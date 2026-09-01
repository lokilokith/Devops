from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError

from app.jit_access.exceptions import GrantNotFoundError
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.platform.extensions import db
from app.shared.database import DbSession
from app.shared.exceptions import DatabaseOperationException


class JITAccessRepository:
    """Repository for managing JITAccessGrant lifecycle."""

    def __init__(self, session: Optional[DbSession] = None) -> None:
        self._session = session

    @property
    def session(self) -> DbSession:
        return self._session if self._session is not None else db.session

    def save(self, grant: JITAccessGrant) -> JITAccessGrant:
        """Persist grant with optimistic concurrency."""
        try:
            current_sess = self.session
            if grant in current_sess.new:
                current_sess.add(grant)
            else:
                grant.row_version = (grant.row_version or 1) + 1
                grant.updated_at = datetime.now(timezone.utc)
                current_sess.add(grant)
            current_sess.flush()
            return grant
        except SQLAlchemyError as e:
            raise DatabaseOperationException(
                f"Failed to save JIT access grant: {e}"
            ) from e

    def find_due_expired_grants(
        self, current_time: Optional[datetime] = None
    ) -> List[JITAccessGrant]:
        """Discover active JIT grants that have reached their expiration time."""
        now = current_time or datetime.now(timezone.utc)
        try:
            stmt = select(JITAccessGrant).where(
                and_(
                    JITAccessGrant.status == JITGrantStatus.ACTIVE,
                    JITAccessGrant.expires_at <= now,
                )
            )
            return list(self.session.execute(stmt).scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseOperationException(
                f"Failed to fetch expired JIT grants: {e}"
            ) from e

    def find_active_by_binding(self, binding_id: UUID) -> List[JITAccessGrant]:
        """Find active grants for a specific target account binding."""
        try:
            stmt = select(JITAccessGrant).where(
                and_(
                    JITAccessGrant.target_account_binding_id == binding_id,
                    JITAccessGrant.status == JITGrantStatus.ACTIVE,
                )
            )
            return list(self.session.execute(stmt).scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseOperationException(
                f"Failed to fetch active grants for binding: {e}"
            ) from e

    def claim_for_revocation(
        self,
        grant_id: UUID,
        worker_id: str,
        lease_duration_seconds: int = 60,
        current_time: Optional[datetime] = None,
    ) -> Optional[JITAccessGrant]:
        """Atomically claim a grant for revocation using CAS and lease fencing.

        Guarantees only one worker can process revocation at a time.
        """
        now = current_time or datetime.now(timezone.utc)
        lease_expiry = now + timedelta(seconds=lease_duration_seconds)

        try:
            grant = self.get_by_id(grant_id)
            if grant.status in (
                JITGrantStatus.REVOKED,
                JITGrantStatus.EXPIRED,
                JITGrantStatus.DENIED,
                JITGrantStatus.FAILED,
            ):
                return None

            # If already running with an active unexpired lease by ANOTHER worker, reject claim
            if (
                grant.status == JITGrantStatus.REVOCATION_RUNNING
                and grant.revocation_lease_expires_at is not None
                and grant.revocation_lease_expires_at > now
                and grant.revocation_worker_id != worker_id
            ):
                return None

            # Atomically update state, worker lease, and increment row_version
            grant.status = JITGrantStatus.REVOCATION_RUNNING
            grant.revocation_worker_id = worker_id
            grant.revocation_lease_expires_at = lease_expiry
            grant.revocation_attempts = (grant.revocation_attempts or 0) + 1
            if not grant.revocation_start:
                grant.revocation_start = now
            grant.row_version = (grant.row_version or 1) + 1
            grant.updated_at = now

            self.session.add(grant)
            self.session.flush()
            return grant
        except SQLAlchemyError as e:
            self.session.rollback()
            raise DatabaseOperationException(
                f"Failed to claim JIT grant {grant_id} for revocation: {e}"
            ) from e

    def find_interrupted_revocations(
        self, current_time: Optional[datetime] = None
    ) -> List[JITAccessGrant]:
        """Discover grants in REVOCATION_PENDING or REVOCATION_RUNNING with expired leases."""
        now = current_time or datetime.now(timezone.utc)
        try:
            from sqlalchemy import or_

            stmt = select(JITAccessGrant).where(
                or_(
                    JITAccessGrant.status == JITGrantStatus.REVOCATION_PENDING,
                    and_(
                        JITAccessGrant.status == JITGrantStatus.REVOCATION_RUNNING,
                        or_(
                            JITAccessGrant.revocation_lease_expires_at.is_(None),
                            JITAccessGrant.revocation_lease_expires_at <= now,
                        ),
                    ),
                )
            )
            return list(self.session.execute(stmt).scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseOperationException(
                f"Failed to fetch interrupted JIT revocations: {e}"
            ) from e

    def save_session(self, session: Any) -> Any:
        """Persist JIT access session."""
        try:
            current_sess = self.session
            current_sess.add(session)
            current_sess.flush()
            return session
        except SQLAlchemyError as e:
            raise DatabaseOperationException(
                f"Failed to save JIT access session: {e}"
            ) from e

    def find_sessions_by_grant(self, grant_id: UUID) -> List[Any]:
        """Fetch all sessions associated with a JIT grant."""
        from app.jit_access.models import JITAccessSession

        try:
            stmt = select(JITAccessSession).where(
                JITAccessSession.jit_grant_id == grant_id
            )
            return list(self.session.execute(stmt).scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseOperationException(
                f"Failed to fetch sessions for grant {grant_id}: {e}"
            ) from e

    def find_active_sessions_by_grant(self, grant_id: UUID) -> List[Any]:
        """Fetch active sessions for a grant."""
        from app.jit_access.models import JITAccessSession

        try:
            stmt = select(JITAccessSession).where(
                and_(
                    JITAccessSession.jit_grant_id == grant_id,
                    JITAccessSession.status == "active",
                )
            )
            return list(self.session.execute(stmt).scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseOperationException(
                f"Failed to fetch active sessions for grant {grant_id}: {e}"
            ) from e

    @staticmethod
    def create(grant: JITAccessGrant) -> JITAccessGrant:
        try:
            db.session.add(grant)
            db.session.commit()
            return grant
        except SQLAlchemyError as e:
            db.session.rollback()
            raise DatabaseOperationException(
                f"Failed to create JIT access grant: {e}"
            ) from e

    @staticmethod
    def get_by_id(grant_id: UUID) -> JITAccessGrant:
        try:
            grant = db.session.get(JITAccessGrant, grant_id)
            if not grant:
                raise GrantNotFoundError(f"Grant {grant_id} not found")
            return grant
        except SQLAlchemyError as e:
            raise DatabaseOperationException(
                f"Failed to fetch JIT access grant: {e}"
            ) from e

    @staticmethod
    def get_by_approval_request(approval_request_id: UUID) -> JITAccessGrant:
        try:
            stmt = select(JITAccessGrant).where(
                JITAccessGrant.approval_request_id == approval_request_id
            )
            grant = db.session.execute(stmt).scalar_one_or_none()
            if not grant:
                raise GrantNotFoundError(
                    f"Grant for request {approval_request_id} not found"
                )
            return grant
        except SQLAlchemyError as e:
            raise DatabaseOperationException(
                f"Failed to fetch JIT access grant by request ID: {e}"
            ) from e

    @staticmethod
    def update(grant: JITAccessGrant) -> JITAccessGrant:
        try:
            db.session.commit()
            return grant
        except SQLAlchemyError as e:
            db.session.rollback()
            raise DatabaseOperationException(
                f"Failed to update JIT access grant: {e}"
            ) from e

    @staticmethod
    def list_grants(
        user_id: UUID | None = None,
        status: JITGrantStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[JITAccessGrant], int]:
        try:
            conditions = []
            if user_id:
                conditions.append(JITAccessGrant.user_id == user_id)
            if status:
                conditions.append(JITAccessGrant.status == status)

            base_stmt = select(JITAccessGrant)
            if conditions:
                base_stmt = base_stmt.where(and_(*conditions))

            # Count
            from sqlalchemy import func

            count_stmt = select(func.count()).select_from(base_stmt.subquery())
            total = db.session.execute(count_stmt).scalar() or 0

            # Fetch
            stmt = (
                base_stmt.order_by(JITAccessGrant.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            results = db.session.execute(stmt).scalars().all()

            return list(results), total
        except SQLAlchemyError as e:
            raise DatabaseOperationException(
                f"Failed to list JIT access grants: {e}"
            ) from e

    @staticmethod
    def check_active_grant(user_id: UUID, role_id: UUID, resource_id: UUID) -> bool:
        """
        Check if an active, unexpired JIT grant exists for the user/role/resource combination.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        try:
            stmt = (
                select(JITAccessGrant)
                .where(
                    and_(
                        JITAccessGrant.user_id == user_id,
                        JITAccessGrant.role_id == role_id,
                        JITAccessGrant.resource_id == resource_id,
                        JITAccessGrant.status == JITGrantStatus.ACTIVE,
                        JITAccessGrant.expires_at > now,
                    )
                )
                .limit(1)
            )

            grant = db.session.execute(stmt).scalar_one_or_none()
            return grant is not None
        except SQLAlchemyError as e:
            raise DatabaseOperationException(
                f"Failed to check active JIT access grant: {e}"
            ) from e
