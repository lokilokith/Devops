"""Due-Rotation Discovery and Idempotent Job Scheduler for OpsForge."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.resources.models import Resource
from app.shared.database import DbSession
from app.vault.domain import SecretStatus
from app.vault.models import VaultSecret
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault_lifecycle.models import (
    RotationStatus,
    SecretRotationPolicy,
)
from app.vault_lifecycle.repository import SecretRotationPolicyRepository
from app.vault_lifecycle.rotation_job import (
    RotationJob,
    RotationJobState,
)
from app.vault_lifecycle.rotation_job_repository import RotationJobRepository

logger = logging.getLogger(__name__)

SCHEDULER_ACTOR_ID: UUID = UUID("00000000-0000-0000-0000-000000000002")


class RotationScheduler:
    """Discovers credentials due for rotation and idempotently enqueues durable rotation jobs."""

    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._policy_repo = SecretRotationPolicyRepository(session)
        self._job_repo = RotationJobRepository(session)
        self._secret_repo = SqlAlchemyVaultRepository(session)

    def discover_due_policies(
        self, current_time: Optional[datetime] = None
    ) -> List[SecretRotationPolicy]:
        """Discover all active policies whose scheduled rotation time is reached."""
        now = current_time or datetime.now(timezone.utc)
        stmt = (
            select(SecretRotationPolicy)
            .where(
                SecretRotationPolicy.status == RotationStatus.ACTIVE,
                SecretRotationPolicy.next_rotation_at <= now,
            )
            .order_by(SecretRotationPolicy.next_rotation_at.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def verify_eligibility(
        self, policy: SecretRotationPolicy
    ) -> Tuple[bool, Optional[str], Optional[VaultSecret]]:
        """Verify that a credential and its target resource are strictly eligible for rotation.

        Fails closed on any inconsistency, missing resource, or conflicting state.
        """
        secret_id = policy.vault_secret_id
        secret_id_str = str(secret_id)

        # 1. Verify Secret exists
        secret_model = self._session.get(VaultSecret, secret_id)
        if not secret_model:
            return False, f"Secret {secret_id_str} not found in database", None

        # 2. Verify Secret lifecycle status allows rotation
        if secret_model.status != SecretStatus.ACTIVE:
            return (
                False,
                f"Secret {secret_id_str} status is {secret_model.status.value}, not ACTIVE",
                secret_model,
            )

        # 3. Verify Secret has a valid current version
        if not secret_model.current_version_id:
            return (
                False,
                f"Secret {secret_id_str} has no active current version",
                secret_model,
            )

        # 4. Verify associated Resource exists and is valid
        resource = self._session.get(Resource, secret_model.resource_id)
        if not resource:
            return (
                False,
                f"Target resource {secret_model.resource_id} not found for secret {secret_id_str}",
                secret_model,
            )

        # 5. Check if there is already an active rotation job
        active_job = self._job_repo.get_active_job_for_secret(secret_id)
        if active_job:
            return (
                False,
                f"Secret {secret_id_str} already has an active rotation job ({active_job.id}, state={active_job.state.value})",
                secret_model,
            )

        return True, None, secret_model

    def create_rotation_job(
        self,
        policy: SecretRotationPolicy,
        secret_model: VaultSecret,
        correlation_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> Tuple[Optional[RotationJob], bool]:
        """Idempotently create and persist a durable RotationJob.

        Returns (job, was_created).
        If another scheduler raced and created the job for the same generation,
        the duplicate is safely caught by the DB uniqueness constraint and returned.
        """
        current_time = now or datetime.now(timezone.utc)
        corr_id = correlation_id or str(uuid.uuid4())

        # Determine target rotation generation based on versions count + 1
        secret_aggregate = self._secret_repo.find_by_id(secret_model.id)
        versions_count = len(secret_aggregate.versions) if secret_aggregate else 1
        target_generation = versions_count + 1

        # Check if job already exists for this generation
        existing_job = self._job_repo.get_by_secret_and_generation(
            secret_model.id, target_generation
        )
        if existing_job:
            return existing_job, False

        job = RotationJob(
            id=uuid.uuid4(),
            vault_secret_id=secret_model.id,
            resource_id=secret_model.resource_id,
            rotation_generation=target_generation,
            state=RotationJobState.QUEUED,
            attempt_count=0,
            max_attempts=3,
            correlation_id=corr_id,
            created_at=current_time,
            updated_at=current_time,
            row_version=1,
        )

        savepoint = self._session.begin_nested()
        try:
            self._session.add(job)
            savepoint.commit()
            return job, True
        except IntegrityError:
            savepoint.rollback()
            logger.info(
                "RotationScheduler: Concurrent job creation collision for secret %s gen %d - reclaiming existing",
                secret_model.id,
                target_generation,
            )
            existing = self._job_repo.get_by_secret_and_generation(
                secret_model.id, target_generation
            )
            return existing, False

    def run_scheduler_cycle(
        self,
        audit_service: AuditService,
        actor_id: Optional[UUID] = None,
        current_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Execute a full scheduler sweep: discover, verify, and idempotently queue jobs."""
        actor = actor_id or SCHEDULER_ACTOR_ID
        now = current_time or datetime.now(timezone.utc)
        run_id = str(uuid.uuid4())

        due_policies = self.discover_due_policies(now)
        logger.info(
            "RotationScheduler: run_id=%s found %d due policies",
            run_id,
            len(due_policies),
        )

        metrics: Dict[str, Any] = {
            "run_id": run_id,
            "discovered_due": len(due_policies),
            "jobs_queued": 0,
            "jobs_existing": 0,
            "ineligible_skipped": 0,
            "details": [],
        }

        for policy in due_policies:
            secret_id_str = str(policy.vault_secret_id)
            is_eligible, reason, secret_model = self.verify_eligibility(policy)

            if not is_eligible or not secret_model:
                metrics["ineligible_skipped"] += 1
                metrics["details"].append(
                    {
                        "vault_secret_id": secret_id_str,
                        "status": "ineligible",
                        "reason": reason,
                    }
                )
                logger.info(
                    "RotationScheduler: secret %s ineligible: %s",
                    secret_id_str,
                    reason,
                )
                continue

            job, was_created = self.create_rotation_job(
                policy=policy,
                secret_model=secret_model,
                correlation_id=run_id,
                now=now,
            )

            if job:
                if was_created:
                    metrics["jobs_queued"] += 1
                    status_desc = "queued"
                    action_name = "ROTATION_QUEUED"
                else:
                    metrics["jobs_existing"] += 1
                    status_desc = "already_active"
                    action_name = "ROTATION_SCHEDULED"

                metrics["details"].append(
                    {
                        "vault_secret_id": secret_id_str,
                        "job_id": str(job.id),
                        "rotation_generation": job.rotation_generation,
                        "status": status_desc,
                    }
                )

                audit_service.log_event(
                    actor_user_id=actor,
                    action=action_name,
                    resource_type="vault_secrets",
                    resource_id=secret_id_str,
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.INFO,
                    details={
                        "run_id": run_id,
                        "job_id": str(job.id),
                        "resource_id": str(secret_model.resource_id),
                        "rotation_generation": job.rotation_generation,
                        "state": job.state.value,
                    },
                )

        self._session.commit()
        return metrics


__all__ = ["RotationScheduler", "SCHEDULER_ACTOR_ID"]
