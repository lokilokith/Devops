import sqlalchemy as sa
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

metadata = sa.MetaData()

t = sa.Table(
    'test', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('col', sa.Enum('A', 'B', name='my_enum', create_type=False))
)

print("--- sa.Enum with create_type=False ---")
print(CreateTable(t).compile(dialect=postgresql.dialect()))

t2 = sa.Table(
    'test2', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('col', postgresql.ENUM('A', 'B', name='my_enum2', create_type=False))
)

print("--- postgresql.ENUM with create_type=False ---")
print(CreateTable(t2).compile(dialect=postgresql.dialect()))
