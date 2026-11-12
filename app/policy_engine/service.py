"""Policy Engine Service."""

from __future__ import annotations

import ipaddress
import logging
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.authorization.service import AuthorizationService
from app.permissions.models import PermissionAction
from app.policy_engine.exceptions import (
    PolicyNotFoundError,
    PolicyValidationError,
)
from app.policy_engine.models import AccessPolicy, PolicyEffect
from app.policy_engine.repository import PolicyRepository

logger = logging.getLogger(__name__)


class PolicyService:
    def __init__(
        self,
        policy_repo: PolicyRepository,
        auth_service: AuthorizationService,
        audit_service: AuditService,
    ) -> None:
        self._repo = policy_repo
        self._auth_service = auth_service
        self._audit_service = audit_service

    def create_policy(self, data: dict) -> AccessPolicy:
        if self._repo.exists_by_name(data["name"]):
            raise PolicyValidationError(
                f"Policy with name '{data['name']}' already exists"
            )

        policy = AccessPolicy(
            name=data["name"],
            description=data.get("description"),
            conditions=data["conditions"],
            max_duration_seconds=data.get("max_duration_seconds"),
            requires_approval=data.get("requires_approval", True),
            effect=PolicyEffect(data.get("effect", "allow").lower()),
            priority=data.get("priority", 0),
            enabled=data.get("enabled", True),
        )
        return self._repo.create(policy)

    def get_policy(self, policy_id: UUID) -> AccessPolicy:
        policy = self._repo.get_by_id(policy_id)
        if not policy:
            raise PolicyNotFoundError(f"Policy '{policy_id}' not found")
        return policy

    def list_policies(
        self, enabled: bool | None = None, page: int = 1, page_size: int = 100
    ) -> Sequence[AccessPolicy]:
        offset = (page - 1) * page_size
        return self._repo.list_policies(enabled=enabled, offset=offset, limit=page_size)

    def update_policy(self, policy_id: UUID, data: dict) -> AccessPolicy:
        policy = self.get_policy(policy_id)

        if "description" in data:
            policy.description = data["description"]
        if "conditions" in data:
            policy.conditions = data["conditions"]
        if "max_duration_seconds" in data:
            policy.max_duration_seconds = data["max_duration_seconds"]
        if "requires_approval" in data:
            policy.requires_approval = data["requires_approval"]
        if "effect" in data:
            policy.effect = PolicyEffect(data["effect"].lower())
        if "priority" in data:
            policy.priority = data["priority"]
        if "enabled" in data:
            policy.enabled = data["enabled"]

        return self._repo.update(policy)

    def delete_policy(self, policy_id: UUID) -> bool:
        return self._repo.delete(policy_id)

    def _check_ip_condition(self, request_ip: str | None, allowed_ranges: list) -> bool:
        if not request_ip:
            return False
        try:
            req_ip_obj = ipaddress.ip_address(request_ip)
            for cidr in allowed_ranges:
                if req_ip_obj in ipaddress.ip_network(cidr, strict=False):
                    return True
        except ValueError:
            pass
        return False

    def _check_time_condition(
        self, request_time_iso: str | None, allowed_hours: dict
    ) -> bool:
        try:
            if request_time_iso:
                req_time = datetime.fromisoformat(
                    request_time_iso.replace("Z", "+00:00")
                )
            else:
                req_time = datetime.now(timezone.utc)

            # Extract HH:MM
            req_hhmm = req_time.strftime("%H:%M")
            start = allowed_hours.get("start", "00:00")
            end = allowed_hours.get("end", "23:59")

            if start <= end:
                return start <= req_hhmm <= end
            else:
                # Wrap around midnight
                return req_hhmm >= start or req_hhmm <= end
        except Exception as e:
            logger.warning(f"Time condition check failed: {e}")
            return False

    def _check_role_condition(self, user_roles: Sequence, allowed_roles: list) -> bool:
        user_role_codes = [r.role_code for r in user_roles]
        # Any intersection counts as match
        return any(role in user_role_codes for role in allowed_roles)

    def _check_resource_attributes(
        self, resource_env: str | None, policy_env: str
    ) -> bool:
        return bool(resource_env and resource_env == policy_env)

    def _evaluate_conditions(
        self,
        conditions: dict[str, Any],
        user_roles: Sequence[Any],
        context: dict[str, Any],
        resource_attributes: dict[str, Any] | None = None,
    ) -> bool:
        """
        Evaluate if a policy's conditions MATCH the given context.
        All specified conditions in the policy must match (AND logic).
        If conditions dict is empty, it matches universally.
        """
        if not conditions:
            return True

        if "allowed_ip_ranges" in conditions:
            if not self._check_ip_condition(
                context.get("ip"), conditions["allowed_ip_ranges"]
            ):
                return False

        if "allowed_hours" in conditions:
            if not self._check_time_condition(
                context.get("time"), conditions["allowed_hours"]
            ):
                return False

        if "allowed_roles" in conditions:
            if not self._check_role_condition(user_roles, conditions["allowed_roles"]):
                return False

        if "environment" in conditions and resource_attributes:
            if not self._check_resource_attributes(
                resource_attributes.get("environment"), conditions["environment"]
            ):
                return False

        return True

    def evaluate_policy(
        self,
        user_id: UUID,
        resource_id: str,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Evaluate access combining RBAC and ABAC rules.
        """
        if context is None:
            context = {}

        trace: list[str] = []
        decision: dict[str, Any] = {
            "decision": "DENY",
            "reason": "Unknown",
            "policy_id": None,
            "requires_approval": False,
            "max_duration_seconds": None,
            "trace": trace,
        }

        def log_and_return() -> dict[str, Any]:
            status = (
                AuditStatus.SUCCESS
                if decision["decision"] == "ALLOW"
                else AuditStatus.DENIED
            )
            self._audit_service.log_event(
                actor_user_id=user_id,
                action="policy.evaluated",
                resource_type="resource",
                resource_id=resource_id,
                status=status,
                severity=AuditSeverity.INFO,
                details={
                    "action": action,
                    "policy_id": decision["policy_id"],
                    "reason": decision["reason"],
                    "trace": trace,
                    "decision": decision["decision"],
                },
            )
            return decision

        # 1. Base RBAC Check
        trace.append("Checking base RBAC permissions")
        try:
            perm_action = PermissionAction(action.lower())
        except ValueError:
            decision["reason"] = f"Invalid action: {action}"
            trace.append(decision["reason"])
            return log_and_return()

        if not self._auth_service.has_permission(user_id, resource_id, perm_action):
            decision["reason"] = "RBAC permission missing"
            trace.append(decision["reason"])
            return log_and_return()

        trace.append("RBAC permission granted")

        # 2. ABAC Evaluation
        active_policies = self._repo.get_active_policies()

        if not active_policies:
            decision["decision"] = "ALLOW"
            decision["reason"] = "RBAC granted and no active ABAC policies"
            trace.append("No ABAC policies to evaluate")
            return log_and_return()

        user_roles = self._auth_service.get_user_roles(user_id)

        matching_policies = []
        has_any_allow_policy = False

        for p in active_policies:
            if p.effect == PolicyEffect.ALLOW:
                has_any_allow_policy = True

            if self._evaluate_conditions(
                p.conditions,
                user_roles,
                context,
                resource_attributes={"environment": "production"},
            ):
                matching_policies.append(p)

        # Sort matching policies by priority desc
        matching_policies.sort(key=lambda x: x.priority, reverse=True)

        # Evaluate Explicit DENY
        for p in matching_policies:
            if p.effect == PolicyEffect.DENY:
                decision["decision"] = "DENY"
                decision["reason"] = f"Explicit DENY by policy: {p.name}"
                decision["policy_id"] = str(p.id)
                trace.append(decision["reason"])
                return log_and_return()

        # Evaluate Explicit ALLOW
        for p in matching_policies:
            if p.effect == PolicyEffect.ALLOW:
                decision["decision"] = "ALLOW"
                decision["reason"] = f"ALLOW by policy: {p.name}"
                decision["policy_id"] = str(p.id)
                decision["requires_approval"] = p.requires_approval
                decision["max_duration_seconds"] = p.max_duration_seconds
                trace.append(decision["reason"])
                return log_and_return()

        # No matching policies.
        # If the system has ANY ALLOW policies, and we didn't match them, implicit DENY.
        if has_any_allow_policy:
            decision["decision"] = "DENY"
            decision["reason"] = "Implicit DENY: matched no ALLOW policies"
            trace.append("No applicable ALLOW policies found for context")
            return log_and_return()

        # No ALLOW policies exist, and no DENY policies matched. Base RBAC allows.
        decision["decision"] = "ALLOW"
        decision["reason"] = "RBAC granted and no matching DENY policies"
        trace.append("ABAC evaluated (no ALLOW policies required)")
        return log_and_return()


__all__ = ["PolicyService"]
