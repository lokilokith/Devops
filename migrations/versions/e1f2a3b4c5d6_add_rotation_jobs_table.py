"""Add rotation_jobs table for Phase 5 automated rotation engine

Revision ID: e1f2a3b4c5d6
Revises: 7a8b9c0d1e2f
Create Date: 2026-08-31 17:15:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = '7a8b9c0d1e2f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'rotation_jobs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('vault_secret_id', sa.Uuid(), nullable=False),
        sa.Column('resource_id', sa.Uuid(), nullable=False),
        sa.Column('rotation_generation', sa.Integer(), nullable=False, server_default='1'),
        sa.Column(
            'state',
            sa.Enum(
                'QUEUED',
                'RUNNING',
                'SUCCEEDED',
                'RETRY_PENDING',
                'FAILED',
                'SECURITY_UNCERTAINTY',
                name='rotation_job_state_enum',
                native_enum=False,
                create_constraint=True,
                validate_strings=True,
            ),
            nullable=False,
            server_default='QUEUED',
        ),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('lease_owner', sa.String(length=255), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lease_generation', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_code', sa.String(length=100), nullable=True),
        sa.Column('last_error_classification', sa.String(length=100), nullable=True),
        sa.Column('correlation_id', sa.String(length=64), nullable=True),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['resource_id'],
            ['resources.id'],
            name=op.f('fk_rotation_jobs_resources_resource_id'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['vault_secret_id'],
            ['vault_secrets.id'],
            name=op.f('fk_rotation_jobs_vault_secrets_vault_secret_id'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_rotation_jobs')),
        sa.UniqueConstraint(
            'vault_secret_id',
            'rotation_generation',
            name='uq_rotation_jobs_secret_generation',
        ),
    )
    with op.batch_alter_table('rotation_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_rotation_jobs_vault_secret_id'), ['vault_secret_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_rotation_jobs_resource_id'), ['resource_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_rotation_jobs_state'), ['state'], unique=False)
        batch_op.create_index('ix_rotation_jobs_state_retry', ['state', 'next_retry_at'], unique=False)
        batch_op.create_index('ix_rotation_jobs_lease', ['state', 'lease_expires_at'], unique=False)


def downgrade():
    with op.batch_alter_table('rotation_jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_rotation_jobs_lease')
        batch_op.drop_index('ix_rotation_jobs_state_retry')
        batch_op.drop_index(batch_op.f('ix_rotation_jobs_state'))
        batch_op.drop_index(batch_op.f('ix_rotation_jobs_resource_id'))
        batch_op.drop_index(batch_op.f('ix_rotation_jobs_vault_secret_id'))

    op.drop_table('rotation_jobs')
