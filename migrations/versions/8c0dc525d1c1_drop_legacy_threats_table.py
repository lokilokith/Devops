"""Drop legacy threats table.

Revision ID: 8c0dc525d1c1
Revises: 8fbc37b7aa74
Create Date: 2026-07-25 10:04:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "8c0dc525d1c1"
down_revision = "8fbc37b7aa74"
branch_labels = None
depends_on = None


def upgrade():
    """Drop the threats table and associated enums."""
    # Drop indexes first
    with op.batch_alter_table("threats", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_threats_threat_level")
        )
        batch_op.drop_index(batch_op.f("ix_threats_status"))
        batch_op.drop_index(
            batch_op.f("ix_threats_indicator")
        )
        batch_op.drop_index(
            batch_op.f("ix_threats_created_at")
        )

    op.drop_table("threats")

    # Drop enums (PostgreSQL only; no-op on SQLite)
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        sa.Enum(name="threat_level_enum").drop(
            connection, checkfirst=True
        )
        sa.Enum(name="threat_status_enum").drop(
            connection, checkfirst=True
        )


def downgrade():
    """Recreate the threats table for rollback."""
    # Recreate enums
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        sa.Enum(
            "low",
            "medium",
            "high",
            "critical",
            name="threat_level_enum",
        ).create(connection, checkfirst=True)
        sa.Enum(
            "Open",
            "Investigating",
            "Contained",
            "Closed",
            "False Positive",
            name="threat_status_enum",
        ).create(connection, checkfirst=True)

    op.create_table(
        "threats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "indicator", sa.String(length=512), nullable=False
        ),
        sa.Column(
            "indicator_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "threat_level",
            sa.Enum(
                "low",
                "medium",
                "high",
                "critical",
                name="threat_level_enum",
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("mitre_attack", sa.String(length=50)),
        sa.Column(
            "source", sa.String(length=256), nullable=False
        ),
        sa.Column("analyst_notes", sa.Text()),
        sa.Column("assigned_analyst", sa.String(length=128)),
        sa.Column(
            "status",
            sa.Enum(
                "Open",
                "Investigating",
                "Contained",
                "Closed",
                "False Positive",
                name="threat_status_enum",
            ),
            server_default="Open",
        ),
        sa.Column("tags", sa.JSON()),
        sa.Column("first_seen", sa.DateTime()),
        sa.Column("last_seen", sa.DateTime()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column("updated_at", sa.DateTime()),
    )

    with op.batch_alter_table(
        "threats", schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_threats_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_threats_indicator"),
            ["indicator"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_threats_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_threats_threat_level"),
            ["threat_level"],
            unique=False,
        )
