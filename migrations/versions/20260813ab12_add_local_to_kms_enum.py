"""Add LOCAL provider to KMS provider type enum.

This migration adds the literal value ``local`` to the ``kms_provider_type_enum``
PostgreSQL enum used by the ``kms_configurations`` table. It is required for the
Phase 2B.4 KMS factory to resolve a ``LOCAL`` configuration without raising an
``UnsupportedKMSProviderError``.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '20260813ab12'
# The previous migration that created the enum is ``bb0ca7658bd4_phase_2b_1_database_foundation``.
# Use its revision id as the down‑revision.

down_revision = 'bb0ca7658bd4'
branch_labels = None
depends_on = None


def upgrade():
    # In bb0ca7658bd4, the enum was created with native_enum=False, meaning it's a VARCHAR with a CHECK constraint.
    conn = op.get_bind()
    res = conn.execute(sa.text("SELECT conname FROM pg_constraint WHERE conrelid = 'kms_configurations'::regclass AND contype = 'c';"))
    for row in res:
        op.execute(f"ALTER TABLE kms_configurations DROP CONSTRAINT {row[0]}")
    op.create_check_constraint(
        'ck_kms_configurations_kms_provider_type_enum',
        'kms_configurations',
        sa.text("provider_type IN ('aws_kms', 'azure_kv', 'hashicorp', 'local')")
    )

def downgrade():
    conn = op.get_bind()
    res = conn.execute(sa.text("SELECT conname FROM pg_constraint WHERE conrelid = 'kms_configurations'::regclass AND contype = 'c';"))
    for row in res:
        op.execute(f"ALTER TABLE kms_configurations DROP CONSTRAINT {row[0]}")
    op.create_check_constraint(
        'ck_kms_configurations_kms_provider_type_enum',
        'kms_configurations',
        sa.text("provider_type IN ('aws_kms', 'azure_kv', 'hashicorp')")
    )
