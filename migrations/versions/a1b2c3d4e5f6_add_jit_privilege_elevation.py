"""feat(phase7): add jit privilege elevation fields

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-08-31 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('jit_access_grants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('target_account_binding_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('command_set_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('revocation_start', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('revocation_complete', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('observed_overrun_ms', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('row_version', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('failure_reason', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('correlation_id', sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            'fk_jit_access_grants_target_account_bindings_binding_id',
            'target_account_bindings',
            ['target_account_binding_id'],
            ['id'],
            ondelete='RESTRICT',
        )
        batch_op.create_index('ix_jit_access_grants_target_account_binding_id', ['target_account_binding_id'])


def downgrade() -> None:
    with op.batch_alter_table('jit_access_grants', schema=None) as batch_op:
        batch_op.drop_index('ix_jit_access_grants_target_account_binding_id')
        batch_op.drop_constraint('fk_jit_access_grants_target_account_bindings_binding_id', type_='foreignkey')
        batch_op.drop_column('correlation_id')
        batch_op.drop_column('failure_reason')
        batch_op.drop_column('row_version')
        batch_op.drop_column('observed_overrun_ms')
        batch_op.drop_column('revocation_complete')
        batch_op.drop_column('revocation_start')
        batch_op.drop_column('command_set_id')
        batch_op.drop_column('target_account_binding_id')
