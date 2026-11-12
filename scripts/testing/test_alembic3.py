import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
import sys

ctx = MigrationContext.configure(dialect=postgresql.dialect(), opts={"as_sql": True})
op = Operations(ctx)

t = op.create_table(
    "threats",
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column(
        "indicator_type",
        sa.Enum("ip", "domain", "hash", "url", name="indicator_type_enum"),
        nullable=False,
    ),
    sa.Column(
        "threat_level",
        sa.Enum("low", "medium", "high", "critical", name="threat_level_enum"),
        nullable=False,
    ),
    sa.PrimaryKeyConstraint("id"),
)
