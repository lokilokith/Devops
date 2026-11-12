import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
import sys

metadata = sa.MetaData(naming_convention={
    "ck": "ck_%(table_name)s_%(constraint_name)s"
})

ctx = MigrationContext.configure(dialect=postgresql.dialect(), opts={"as_sql": True, "target_metadata": metadata})
op = Operations(ctx)

with op.batch_alter_table("permissions") as batch_op:
    batch_op.drop_constraint("permission_action_enum", type_="check")
