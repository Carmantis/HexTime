"""check team role values

Adds the CHECK constraint that Enum(native_enum=False) was supposed to bring
along. Without it `role` is a bare VARCHAR(10) and accepts any string, on both
SQLite and PostgreSQL.

Written by hand: Alembic's autogenerate does not compare CHECK constraints, so
this difference is invisible to `alembic check`.

Revision ID: 7b2c1d9e4a10
Revises: 63fd791cc137
Create Date: 2026-09-27

"""

from collections.abc import Sequence

from alembic import op

revision: str = "7b2c1d9e4a10"
down_revision: str | Sequence[str] | None = "63fd791cc137"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Both tables store a role, and both used the same unvalidated column.
TABLES = ("team_members", "invitations")

CONSTRAINT = "team_role"
CONDITION = "role IN ('member', 'lead', 'admin')"


def upgrade() -> None:
    for table in TABLES:
        # batch mode rebuilds the table on SQLite, which cannot ALTER in a
        # constraint, and emits a plain ALTER TABLE on PostgreSQL.
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.create_check_constraint(CONSTRAINT, CONDITION)


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(CONSTRAINT, type_="check")
