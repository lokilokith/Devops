"""Add FAILED and SECURITY_UNCERTAIN to JITGrantStatus

Revision ID: 4f5394bb6534
Revises: 3f4294aa5423
Create Date: 2026-09-06 15:30:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '4f5394bb6534'
down_revision = '3f4294aa5423'
branch_labels = None
depends_on = None

def _drop_status_constraint():
    op.drop_constraint(
        "ck_jit_access_grants_jit_grant_status_enum",
        "jit_access_grants",
        type_="check",
    )


def upgrade():
    # Widen status column to accommodate longer statuses (e.g. security_uncertain: 18 chars)
    op.alter_column('jit_access_grants', 'status', type_=sa.String(32), existing_type=sa.String(7), existing_nullable=False)
    # Update check constraint
    _drop_status_constraint()
    op.execute("ALTER TABLE jit_access_grants ADD CONSTRAINT ck_jit_access_grants_jit_grant_status_enum CHECK (status IN ('pending', 'active', 'revocation_pending', 'revocation_running', 'expired', 'revoked', 'denied', 'failed', 'security_uncertain'))")


def downgrade():
    bind = op.get_bind()
    count = bind.execute(sa.text(
        "SELECT COUNT(*) FROM jit_access_grants WHERE status IN ('failed', 'security_uncertain', 'revocation_pending', 'revocation_running')"
    )).scalar()
    if count and count > 0:
        raise RuntimeError(
            f"Cannot downgrade migration 4f5394bb6534: {count} row(s) in jit_access_grants have "
            f"statuses introduced by this migration ('failed', 'security_uncertain', 'revocation_pending', 'revocation_running'). "
            f"Downgrading without data handling would cause data loss or constraint violation. "
            f"Remediate or archive these rows before downgrade."
        )
    _drop_status_constraint()
    op.execute("ALTER TABLE jit_access_grants ADD CONSTRAINT ck_jit_access_grants_jit_grant_status_enum CHECK (status IN ('pending', 'active', 'expired', 'revoked', 'denied'))")
    op.alter_column('jit_access_grants', 'status', type_=sa.String(7), existing_type=sa.String(32), existing_nullable=False)
