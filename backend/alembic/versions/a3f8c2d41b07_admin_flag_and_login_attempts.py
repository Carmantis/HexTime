"""admin flag and login attempts

Server-mode sign-in (phase 7.1): an organisation administrator flag on users,
and a table of recent failed logins for rate limiting.

Revision ID: a3f8c2d41b07
Revises: 7b2c1d9e4a10
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3f8c2d41b07"
down_revision: str | Sequence[str] | None = "7b2c1d9e4a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A server default fills in the existing rows: nobody is an admin yet.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    op.create_table(
        "login_attempts",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("login_attempts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_login_attempts_email"), ["email"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_login_attempts_attempted_at"), ["attempted_at"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("login_attempts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_login_attempts_attempted_at"))
        batch_op.drop_index(batch_op.f("ix_login_attempts_email"))
    op.drop_table("login_attempts")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("is_admin")
