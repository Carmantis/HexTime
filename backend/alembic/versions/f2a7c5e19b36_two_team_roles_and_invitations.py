"""two team roles and invitations

Decided 2026-10-08: a team has leads and members, nothing more. Whoever
creates a team is its lead, and a lead invites people who are already in the
organisation; they join only by saying yes in the app.

Existing team admins become leads, which keeps every right they used.

Revision ID: f2a7c5e19b36
Revises: e4b9d2f6a813
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a7c5e19b36"
down_revision: str | Sequence[str] | None = "e4b9d2f6a813"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "team_role"


def _roles(condition: str) -> None:
    # batch mode rebuilds the table on SQLite, which cannot ALTER a
    # constraint, and emits plain ALTER TABLE statements on PostgreSQL.
    with op.batch_alter_table("team_members", schema=None) as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_="check")
        batch_op.create_check_constraint(CONSTRAINT, condition)


def upgrade() -> None:
    op.execute("UPDATE team_members SET role = 'lead' WHERE role = 'admin'")
    _roles("role IN ('member', 'lead')")

    op.create_table(
        "team_invitations",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("team_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("team_invitations")
    # Leads stay leads: the old admin role cannot be told apart any more.
    _roles("role IN ('member', 'lead', 'admin')")
