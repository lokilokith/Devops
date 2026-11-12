from sqlalchemy import and_, or_, select

from app.database import SessionLocal
from app.jit_access.models import JITAccessGrant, JITGrantStatus, JITReconciliationState


def main():
    session = SessionLocal()
    now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
    stmt_uncertain = select(JITAccessGrant.id).outerjoin(
        JITReconciliationState
    ).where(
        and_(
            JITAccessGrant.status == JITGrantStatus.SECURITY_UNCERTAIN,
            or_(
                JITReconciliationState.grant_id == None,
                JITReconciliationState.lease_expires_at == None,
                JITReconciliationState.lease_expires_at <= now,
            )
        )
    ).limit(50)
    print("SQL:", stmt_uncertain)
    results = session.execute(stmt_uncertain).scalars().all()
    print("RESULTS:", results)

if __name__ == '__main__':
    main()
