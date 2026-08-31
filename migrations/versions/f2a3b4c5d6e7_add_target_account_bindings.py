"""add target_account_bindings table

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-31 17:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'target_account_bindings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('control_plane_user_id', sa.Uuid(), nullable=False),
        sa.Column('resource_id', sa.Uuid(), nullable=False),
        sa.Column('target_os_username', sa.String(length=32), nullable=False),
        sa.Column('ssh_credential_id', sa.Uuid(), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'pending',
                'active',
                'suspended',
                'removed',
                name='target_account_binding_status_enum',
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default='pending',
        ),
        sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_reason', sa.String(length=1000), nullable=True),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['control_plane_user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['resource_id'], ['resources.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['ssh_credential_id'], ['vault_secrets.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('control_plane_user_id', 'resource_id', name='uq_target_account_user_resource'),
        sa.UniqueConstraint('resource_id', 'target_os_username', name='uq_target_account_resource_os_user'),
    )
    op.create_index('ix_target_account_bindings_control_plane_user_id', 'target_account_bindings', ['control_plane_user_id'])
    op.create_index('ix_target_account_bindings_resource_id', 'target_account_bindings', ['resource_id'])
    op.create_index('ix_target_account_bindings_target_os_username', 'target_account_bindings', ['target_os_username'])
    op.create_index('ix_target_account_bindings_status', 'target_account_bindings', ['status'])
    op.create_index('ix_target_account_bindings_ssh_credential_id', 'target_account_bindings', ['ssh_credential_id'])


def downgrade() -> None:
    op.drop_index('ix_target_account_bindings_ssh_credential_id', table_name='target_account_bindings')
    op.drop_index('ix_target_account_bindings_status', table_name='target_account_bindings')
    op.drop_index('ix_target_account_bindings_target_os_username', table_name='target_account_bindings')
    op.drop_index('ix_target_account_bindings_resource_id', table_name='target_account_bindings')
    op.drop_index('ix_target_account_bindings_control_plane_user_id', table_name='target_account_bindings')
    op.drop_table('target_account_bindings')
