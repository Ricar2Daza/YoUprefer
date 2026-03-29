"""Add follow and notifications tables

Revision ID: 1d2f3a4b5c67
Revises: dd2684518fdd
Create Date: 2026-02-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "1d2f3a4b5c67"
down_revision: Union[str, Sequence[str], None] = "dd2684518fdd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # follow table
    op.create_table(
        "follow",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("follower_id", sa.Integer(), nullable=False),
        sa.Column("following_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["follower_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["following_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("follower_id", "following_id", name="uq_user_follow"),
    )
    op.create_index(op.f("ix_follow_id"), "follow", ["id"], unique=False)
    op.create_index(op.f("ix_follow_follower_id"), "follow", ["follower_id"], unique=False)
    op.create_index(op.f("ix_follow_following_id"), "follow", ["following_id"], unique=False)

    # notification table
    op.create_table(
        "notification",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_read", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notification_id"), "notification", ["id"], unique=False)
    op.create_index(op.f("ix_notification_user_id"), "notification", ["user_id"], unique=False)
    op.create_index(op.f("ix_notification_type"), "notification", ["type"], unique=False)
    op.create_index(op.f("ix_notification_is_read"), "notification", ["is_read"], unique=False)
    op.create_index(op.f("ix_notification_created_at"), "notification", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_created_at"), table_name="notification")
    op.drop_index(op.f("ix_notification_is_read"), table_name="notification")
    op.drop_index(op.f("ix_notification_type"), table_name="notification")
    op.drop_index(op.f("ix_notification_user_id"), table_name="notification")
    op.drop_index(op.f("ix_notification_id"), table_name="notification")
    op.drop_table("notification")

    op.drop_index(op.f("ix_follow_following_id"), table_name="follow")
    op.drop_index(op.f("ix_follow_follower_id"), table_name="follow")
    op.drop_index(op.f("ix_follow_id"), table_name="follow")
    op.drop_table("follow")
