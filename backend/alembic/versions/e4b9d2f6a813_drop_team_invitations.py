"""drop team invitations

Team invitations were planned as their own token table with an accept step.
Phase 7.5 adds people to a team directly by address instead: someone without
an account gets the same set-password link as any invited person (the
account_tokens table), so this table never got a single row.

Revision ID: e4b9d2f6a813
Revises: c71e5a9b3d24
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e4b9d2f6a813"
down_revision: str | Sequence[str] | None = "c71e5a9b3d24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("invitations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invitations_team_id"))
        batch_op.drop_index(batch_op.f("ix_invitations_email"))
    op.drop_table("invitations")


def downgrade() -> None:
    op.create_table(
        "invitations",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "member",
                "lead",
                "admin",
                name="team_role",
                native_enum=False,
                length=10,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    with op.batch_alter_table("invitations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_invitations_email"), ["email"], unique=False)
        batch_op.create_index(batch_op.f("ix_invitations_team_id"), ["team_id"], unique=False)
