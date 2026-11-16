"""account tokens

One-time links sent by email (phase 7.2): setting the password of an account
an administrator created, resetting a forgotten one, and confirming the
address after signing up yourself.

Revision ID: c71e5a9b3d24
Revises: a3f8c2d41b07
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c71e5a9b3d24"
down_revision: str | Sequence[str] | None = "a3f8c2d41b07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum(
                "setup",
                "reset",
                "verify",
                name="token_purpose",
                native_enum=False,
                length=10,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    with op.batch_alter_table("account_tokens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_account_tokens_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("account_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_account_tokens_user_id"))
    op.drop_table("account_tokens")
