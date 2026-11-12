"""Repository for durable RotationJob lifecycle and atomic leasing."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import or_, select, update

from app.shared.database import DbSession
from app.vault_lifecycle.rotation_job import (
    ACTIVE_JOB_STATES,
    RotationJob,
    RotationJobState,
)

logger = logging.getLogger(__name__)


class RotationJobRepository:
    """SQLAlchemy repository for RotationJob persistence and atomic lease claiming."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def save(self, job: RotationJob) -> RotationJob:
        """Persist job changes with optimistic concurrency verification."""
        if job in self._session.new:
            self._session.add(job)
            return job

        # Check optimistic concurrency
        current_version = job.row_version
        job.row_version = current_version + 1
        job.updated_at = datetime.now(timezone.utc)

        # Flush will trigger DB-level concurrency if version changed under us
        self._session.add(job)
        return job

    def get_by_id(self, job_id: UUID) -> Optional[RotationJob]:
        """Fetch a rotation job by primary key."""
        return self._session.get(RotationJob, job_id)

    def get_active_job_for_secret(self, vault_secret_id: UUID) -> Optional[RotationJob]:
        """Return the active rotation job (QUEUED, RUNNING, or RETRY_PENDING) for a secret."""
        stmt = (
            select(RotationJob)
            .where(
                RotationJob.vault_secret_id == vault_secret_id,
                RotationJob.state.in_(ACTIVE_JOB_STATES),
            )
            .order_by(RotationJob.created_at.desc())
        )
        return self._session.execute(stmt).scalars().first()

    def get_by_secret_and_generation(
        self, vault_secret_id: UUID, generation: int
    ) -> Optional[RotationJob]:
        """Fetch a job by secret ID and specific rotation generation."""
        stmt = select(RotationJob).where(
            RotationJob.vault_secret_id == vault_secret_id,
            RotationJob.rotation_generation == generation,
        )
        return self._session.execute(stmt).scalars().first()

    def find_claimable_jobs(
        self, limit: int = 50, now: Optional[datetime] = None
    ) -> List[RotationJob]:
        """Find jobs that are eligible to be claimed by a worker.

        Includes:
        - state == QUEUED
        - state == RETRY_PENDING and next_retry_at <= now
        - state == RUNNING and lease_expires_at < now (stale lease recovery)
        """
        current_time = now or datetime.now(timezone.utc)
        stmt = (
            select(RotationJob)
            .where(
                or_(
                    RotationJob.state == RotationJobState.QUEUED,
                    (RotationJob.state == RotationJobState.RETRY_PENDING)
                    & (
                        (RotationJob.next_retry_at <= current_time)
                        | (RotationJob.next_retry_at.is_(None))
                    ),
                    (RotationJob.state == RotationJobState.RUNNING)
                    & (RotationJob.lease_expires_at < current_time),
                )
            )
            .order_by(RotationJob.created_at.asc())
            .limit(limit)
        )
        return list(self._session.execute(stmt).scalars().all())

    def atomic_claim(
        self,
        job_id: UUID,
        worker_id: str,
        lease_duration_seconds: int = 300,
        now: Optional[datetime] = None,
    ) -> Optional[RotationJob]:
        """Atomically claim a job lease using SQL CAS.

        Guarantees that exactly one worker receives the lease and fencing generation.
        Returns the freshly reloaded claimed RotationJob or None if claim failed.
        """
        current_time = now or datetime.now(timezone.utc)
        lease_exp = current_time + timedelta(seconds=lease_duration_seconds)

        job = self.get_by_id(job_id)
        if not job:
            return None

        # Verify eligibility in memory before issuing atomic update
        if job.state == RotationJobState.RUNNING and not job.is_lease_expired(
            current_time
        ):
            return None
        if job.state == RotationJobState.RETRY_PENDING:
            if job.next_retry_at and job.next_retry_at > current_time:
                return None
        if job.state in {
            RotationJobState.SUCCEEDED,
            RotationJobState.FAILED,
            RotationJobState.SECURITY_UNCERTAINTY,
        }:
            return None

        expected_row_version = job.row_version
        new_lease_gen = job.lease_generation + 1
        new_attempt_count = job.attempt_count + 1

        # Atomic SQL UPDATE with CAS guard on row_version
        stmt = (
            update(RotationJob)
            .where(
                RotationJob.id == job_id,
                RotationJob.row_version == expected_row_version,
            )
            .values(
                state=RotationJobState.RUNNING,
                lease_owner=worker_id,
                lease_expires_at=lease_exp,
                lease_generation=new_lease_gen,
                attempt_count=new_attempt_count,
                started_at=job.started_at or current_time,
                updated_at=current_time,
                row_version=expected_row_version + 1,
            )
        )
        result = self._session.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        if rowcount == 0:
            logger.debug(
                "RotationJobRepository: CAS claim collision for job %s (expected version %d)",
                job_id,
                expected_row_version,
            )
            return None

        # Reload job state
        self._session.expire(job)
        return self.get_by_id(job_id)

    def verify_fencing(
        self, job_id: UUID, expected_worker_id: str, expected_lease_gen: int
    ) -> bool:
        """Verify that the worker still owns the current lease and fencing token."""
        stmt = select(RotationJob).where(
            RotationJob.id == job_id,
            RotationJob.lease_owner == expected_worker_id,
            RotationJob.lease_generation == expected_lease_gen,
            RotationJob.state == RotationJobState.RUNNING,
        )
        matched = self._session.execute(stmt).scalars().first()
        return matched is not None


__all__ = ["RotationJobRepository"]
