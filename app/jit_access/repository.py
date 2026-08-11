"""JIT Access Repository."""

from typing import List, Tuple
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.exc import SQLAlchemyError

from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.platform.extensions import db
from app.shared.exceptions import DatabaseOperationException
from app.jit_access.exceptions import GrantNotFoundError


class JITAccessRepository:
    """Repository for managing JITAccessGrant lifecycle."""

    @staticmethod
    def create(grant: JITAccessGrant) -> JITAccessGrant:
        try:
            db.session.add(grant)
            db.session.commit()
            return grant
        except SQLAlchemyError as e:
            db.session.rollback()
            raise DatabaseOperationException(f"Failed to create JIT access grant: {e}") from e

    @staticmethod
    def get_by_id(grant_id: UUID) -> JITAccessGrant:
        try:
            grant = db.session.get(JITAccessGrant, grant_id)
            if not grant:
                raise GrantNotFoundError(f"Grant {grant_id} not found")
            return grant
        except SQLAlchemyError as e:
            raise DatabaseOperationException(f"Failed to fetch JIT access grant: {e}") from e

    @staticmethod
    def get_by_approval_request(approval_request_id: UUID) -> JITAccessGrant:
        try:
            stmt = select(JITAccessGrant).where(JITAccessGrant.approval_request_id == approval_request_id)
            grant = db.session.execute(stmt).scalar_one_or_none()
            if not grant:
                raise GrantNotFoundError(f"Grant for request {approval_request_id} not found")
            return grant
        except SQLAlchemyError as e:
            raise DatabaseOperationException(f"Failed to fetch JIT access grant by request ID: {e}") from e

    @staticmethod
    def update(grant: JITAccessGrant) -> JITAccessGrant:
        try:
            db.session.commit()
            return grant
        except SQLAlchemyError as e:
            db.session.rollback()
            raise DatabaseOperationException(f"Failed to update JIT access grant: {e}") from e

    @staticmethod
    def list_grants(
        user_id: UUID | None = None,
        status: JITGrantStatus | None = None,
        limit: int = 50,
        offset: int = 0
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
            stmt = base_stmt.order_by(JITAccessGrant.created_at.desc()).limit(limit).offset(offset)
            results = db.session.execute(stmt).scalars().all()
            
            return list(results), total
        except SQLAlchemyError as e:
            raise DatabaseOperationException(f"Failed to list JIT access grants: {e}") from e

    @staticmethod
    def check_active_grant(user_id: UUID, role_id: UUID, resource_id: UUID) -> bool:
        """
        Check if an active, unexpired JIT grant exists for the user/role/resource combination.
        """
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        try:
            stmt = select(JITAccessGrant).where(
                and_(
                    JITAccessGrant.user_id == user_id,
                    JITAccessGrant.role_id == role_id,
                    JITAccessGrant.resource_id == resource_id,
                    JITAccessGrant.status == JITGrantStatus.ACTIVE,
                    JITAccessGrant.expires_at > now
                )
            ).limit(1)
            
            grant = db.session.execute(stmt).scalar_one_or_none()
            return grant is not None
        except SQLAlchemyError as e:
            raise DatabaseOperationException(f"Failed to check active JIT access grant: {e}") from e
