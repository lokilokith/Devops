import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

ctx = MigrationContext.configure(dialect=postgresql.dialect(), opts={"as_sql": True})
op = Operations(ctx)

print("--- DROP TABLE ---")
op.drop_table("threats")
