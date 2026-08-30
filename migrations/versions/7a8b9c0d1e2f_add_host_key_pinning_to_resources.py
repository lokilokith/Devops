"""Add host key pinning fields to resources

Revision ID: 7a8b9c0d1e2f
Revises: 68ff0eec529a
Create Date: 2026-08-30 21:42:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7a8b9c0d1e2f'
down_revision = '68ff0eec529a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pinned_host_key', sa.String(length=1000), nullable=True))
        batch_op.add_column(sa.Column('host_key_fingerprint', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('host_key_trusted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.drop_column('host_key_trusted_at')
        batch_op.drop_column('host_key_fingerprint')
        batch_op.drop_column('pinned_host_key')
