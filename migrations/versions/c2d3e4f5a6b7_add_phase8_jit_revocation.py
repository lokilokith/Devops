"""feat(phase8): add jit revocation and session enforcement fields

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-31 22:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jit_access_grants", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("revocation_worker_id", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "revocation_lease_expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "revocation_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("sessions_terminated", sa.Integer(), nullable=True)
        )

    with op.batch_alter_table("jit_access_sessions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("jit_grant_id", sa.Uuid(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("resource_id", sa.Uuid(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("target_os_username", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("target_session_pid", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="active",
            )
        )
        batch_op.add_column(
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_jit_access_sessions_jit_access_grants_grant_id",
            "jit_access_grants",
            ["jit_grant_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_jit_access_sessions_resources_resource_id",
            "resources",
            ["resource_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_jit_access_sessions_jit_grant_id", ["jit_grant_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("jit_access_sessions", schema=None) as batch_op:
        batch_op.drop_index("ix_jit_access_sessions_jit_grant_id")
        batch_op.drop_constraint(
            "fk_jit_access_sessions_resources_resource_id",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_jit_access_sessions_jit_access_grants_grant_id",
            type_="foreignkey",
        )
        batch_op.drop_column("terminated_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("status")
        batch_op.drop_column("target_session_pid")
        batch_op.drop_column("target_os_username")
        batch_op.drop_column("resource_id")
        batch_op.drop_column("jit_grant_id")

    with op.batch_alter_table("jit_access_grants", schema=None) as batch_op:
        batch_op.drop_column("sessions_terminated")
        batch_op.drop_column("revocation_attempts")
        batch_op.drop_column("revocation_lease_expires_at")
        batch_op.drop_column("revocation_worker_id")
