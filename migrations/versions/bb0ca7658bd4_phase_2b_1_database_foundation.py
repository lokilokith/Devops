"""Phase 2B.1 Database Foundation

Revision ID: bb0ca7658bd4
Revises: b84b3943a879
Create Date: 2026-08-13 09:38:12.529334

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'bb0ca7658bd4'
down_revision = 'b84b3943a879'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Update secret_status_enum check constraint
    op.drop_constraint('secret_status_enum', 'vault_secrets', type_='check')
    op.create_check_constraint('secret_status_enum', 'vault_secrets',
        sa.text("status IN ('active', 'rotating', 'disabled', 'tombstoned', 'desynced', 'jit_ephemeral')")
    )

    # 2. Add KMS Configuration Table
    op.create_table(
        'kms_configurations',
        sa.Column('id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('provider_type', sa.Enum('aws_kms', 'azure_kv', 'hashicorp', name='kms_provider_type_enum', native_enum=False, create_constraint=True), nullable=False),
        sa.Column('kms_endpoint', sa.String(length=500), nullable=True),
        sa.Column('kms_key_id', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_active_kms', 'kms_configurations', ['is_active'], unique=True, postgresql_where=sa.text('is_active = true'))

    # 3. Update secret_rotation_policies
    op.add_column('secret_rotation_policies', sa.Column('plugin_name', sa.String(length=100), nullable=False, server_default='manual'))
    op.add_column('secret_rotation_policies', sa.Column('rotation_interval_days', sa.Integer(), nullable=False, server_default='30'))
    op.add_column('secret_rotation_policies', sa.Column('last_rotation_status', sa.Enum('success', 'failed', name='rotation_result_status_enum', native_enum=False, create_constraint=True), nullable=True))
    op.add_column('secret_rotation_policies', sa.Column('failure_reason', sa.String(length=1000), nullable=True))

    # 4. Add jit_access_sessions table
    op.create_table(
        'jit_access_sessions',
        sa.Column('id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('access_request_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('ephemeral_secret_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['access_request_id'], ['access_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ephemeral_secret_id'], ['vault_secrets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('access_request_id'),
        sa.UniqueConstraint('ephemeral_secret_id')
    )

    # 5. Add auth_mechanism to resources
    op.add_column('resources', sa.Column('auth_mechanism', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('resources', 'auth_mechanism')
    op.drop_table('jit_access_sessions')

    op.drop_column('secret_rotation_policies', 'failure_reason')
    op.drop_column('secret_rotation_policies', 'last_rotation_status')
    op.drop_column('secret_rotation_policies', 'rotation_interval_days')
    op.drop_column('secret_rotation_policies', 'plugin_name')

    op.drop_index('ix_active_kms', table_name='kms_configurations', postgresql_where=sa.text('is_active = true'))
    op.drop_table('kms_configurations')

    op.drop_constraint('secret_status_enum', 'vault_secrets', type_='check')
    op.create_check_constraint('secret_status_enum', 'vault_secrets',
        sa.text("status IN ('active', 'rotating', 'disabled', 'tombstoned')")
    )
