"""Add blocks, messages, custom votes and user fields

Revision ID: 2b7c8a9d1e2f
Revises: d73584c88322
Create Date: 2026-04-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2b7c8a9d1e2f"
down_revision: Union[str, Sequence[str], None] = "d73584c88322"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("bio", sa.String(), nullable=True))
    op.add_column("user", sa.Column("is_banned", sa.Boolean(), nullable=True, server_default=sa.text("false")))
    op.add_column("user", sa.Column("banned_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("ban_reason", sa.String(), nullable=True))
    op.create_index(op.f("ix_user_is_banned"), "user", ["is_banned"], unique=False)

    op.create_table(
        "userblock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blocker_id", sa.Integer(), nullable=False),
        sa.Column("blocked_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["blocker_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["blocked_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block"),
    )
    op.create_index(op.f("ix_userblock_id"), "userblock", ["id"], unique=False)
    op.create_index(op.f("ix_userblock_blocker_id"), "userblock", ["blocker_id"], unique=False)
    op.create_index(op.f("ix_userblock_blocked_id"), "userblock", ["blocked_id"], unique=False)

    op.create_table(
        "directmessage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["sender_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["recipient_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_directmessage_id"), "directmessage", ["id"], unique=False)
    op.create_index(op.f("ix_directmessage_sender_id"), "directmessage", ["sender_id"], unique=False)
    op.create_index(op.f("ix_directmessage_recipient_id"), "directmessage", ["recipient_id"], unique=False)
    op.create_index(op.f("ix_directmessage_is_read"), "directmessage", ["is_read"], unique=False)
    op.create_index(op.f("ix_directmessage_created_at"), "directmessage", ["created_at"], unique=False)
    op.create_index("ix_direct_message_pair_created", "directmessage", ["sender_id", "recipient_id", "created_at"], unique=False)

    op.create_table(
        "customvote",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expiring_notified", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_customvote_id"), "customvote", ["id"], unique=False)
    op.create_index(op.f("ix_customvote_owner_id"), "customvote", ["owner_id"], unique=False)
    op.create_index(op.f("ix_customvote_category_id"), "customvote", ["category_id"], unique=False)
    op.create_index(op.f("ix_customvote_is_active"), "customvote", ["is_active"], unique=False)
    op.create_index(op.f("ix_customvote_created_at"), "customvote", ["created_at"], unique=False)
    op.create_index(op.f("ix_customvote_expires_at"), "customvote", ["expires_at"], unique=False)

    op.create_table(
        "customvoteparticipant",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vote_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["vote_id"], ["customvote.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vote_id", "user_id", name="uq_custom_vote_participant"),
    )
    op.create_index(op.f("ix_customvoteparticipant_id"), "customvoteparticipant", ["id"], unique=False)
    op.create_index(op.f("ix_customvoteparticipant_vote_id"), "customvoteparticipant", ["vote_id"], unique=False)
    op.create_index(op.f("ix_customvoteparticipant_user_id"), "customvoteparticipant", ["user_id"], unique=False)

    op.create_table(
        "customvotephoto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(), nullable=False),
        sa.Column("object_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["participant_id"], ["customvoteparticipant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_customvotephoto_id"), "customvotephoto", ["id"], unique=False)
    op.create_index(op.f("ix_customvotephoto_participant_id"), "customvotephoto", ["participant_id"], unique=False)
    op.create_index(op.f("ix_customvotephoto_created_at"), "customvotephoto", ["created_at"], unique=False)

    op.create_table(
        "customvoteballot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vote_id", sa.Integer(), nullable=False),
        sa.Column("voter_id", sa.Integer(), nullable=False),
        sa.Column("photo_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["vote_id"], ["customvote.id"]),
        sa.ForeignKeyConstraint(["voter_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["photo_id"], ["customvotephoto.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vote_id", "voter_id", name="uq_custom_vote_ballot"),
    )
    op.create_index(op.f("ix_customvoteballot_id"), "customvoteballot", ["id"], unique=False)
    op.create_index(op.f("ix_customvoteballot_vote_id"), "customvoteballot", ["vote_id"], unique=False)
    op.create_index(op.f("ix_customvoteballot_voter_id"), "customvoteballot", ["voter_id"], unique=False)
    op.create_index(op.f("ix_customvoteballot_photo_id"), "customvoteballot", ["photo_id"], unique=False)
    op.create_index(op.f("ix_customvoteballot_created_at"), "customvoteballot", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_customvoteballot_created_at"), table_name="customvoteballot")
    op.drop_index(op.f("ix_customvoteballot_photo_id"), table_name="customvoteballot")
    op.drop_index(op.f("ix_customvoteballot_voter_id"), table_name="customvoteballot")
    op.drop_index(op.f("ix_customvoteballot_vote_id"), table_name="customvoteballot")
    op.drop_index(op.f("ix_customvoteballot_id"), table_name="customvoteballot")
    op.drop_table("customvoteballot")

    op.drop_index(op.f("ix_customvotephoto_created_at"), table_name="customvotephoto")
    op.drop_index(op.f("ix_customvotephoto_participant_id"), table_name="customvotephoto")
    op.drop_index(op.f("ix_customvotephoto_id"), table_name="customvotephoto")
    op.drop_table("customvotephoto")

    op.drop_index(op.f("ix_customvoteparticipant_user_id"), table_name="customvoteparticipant")
    op.drop_index(op.f("ix_customvoteparticipant_vote_id"), table_name="customvoteparticipant")
    op.drop_index(op.f("ix_customvoteparticipant_id"), table_name="customvoteparticipant")
    op.drop_table("customvoteparticipant")

    op.drop_index(op.f("ix_customvote_expires_at"), table_name="customvote")
    op.drop_index(op.f("ix_customvote_created_at"), table_name="customvote")
    op.drop_index(op.f("ix_customvote_is_active"), table_name="customvote")
    op.drop_index(op.f("ix_customvote_category_id"), table_name="customvote")
    op.drop_index(op.f("ix_customvote_owner_id"), table_name="customvote")
    op.drop_index(op.f("ix_customvote_id"), table_name="customvote")
    op.drop_table("customvote")

    op.drop_index("ix_direct_message_pair_created", table_name="directmessage")
    op.drop_index(op.f("ix_directmessage_created_at"), table_name="directmessage")
    op.drop_index(op.f("ix_directmessage_is_read"), table_name="directmessage")
    op.drop_index(op.f("ix_directmessage_recipient_id"), table_name="directmessage")
    op.drop_index(op.f("ix_directmessage_sender_id"), table_name="directmessage")
    op.drop_index(op.f("ix_directmessage_id"), table_name="directmessage")
    op.drop_table("directmessage")

    op.drop_index(op.f("ix_userblock_blocked_id"), table_name="userblock")
    op.drop_index(op.f("ix_userblock_blocker_id"), table_name="userblock")
    op.drop_index(op.f("ix_userblock_id"), table_name="userblock")
    op.drop_table("userblock")

    op.drop_index(op.f("ix_user_is_banned"), table_name="user")
    op.drop_column("user", "ban_reason")
    op.drop_column("user", "banned_until")
    op.drop_column("user", "is_banned")
    op.drop_column("user", "bio")

