"""Add retry_count to secret_rotation_policies

Revision ID: 911dfe68a5cb
Revises: 20260813ab12
Create Date: 2026-08-13 17:13:51.294935

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '911dfe68a5cb'
down_revision = '20260813ab12'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'secret_rotation_policies',
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0')
    )


def downgrade():
    op.drop_column('secret_rotation_policies', 'retry_count')
