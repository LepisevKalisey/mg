"""create core tables

Revision ID: 0001
Revises: 
Create Date: 2023-10-08
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), server_onupdate=sa.func.now(), nullable=False),
    )

    op.create_table(
        "secrets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("enc_value", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), server_onupdate=sa.func.now(), nullable=False),
    )

    op.create_table(
        "master_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("enc_session", sa.LargeBinary, nullable=False),
        sa.Column("valid", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), server_onupdate=sa.func.now(), nullable=False),
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tg_id", sa.BigInteger, nullable=False),
        sa.Column("username", sa.Text),
        sa.Column("title", sa.Text),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("trust_level", sa.Integer),
        sa.Column("added_by", sa.BigInteger),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "raw_posts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.BigInteger, sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("tg_message_id", sa.BigInteger, nullable=False),
        sa.Column("author", sa.Text),
        sa.Column("text", sa.Text),
        sa.Column("media", sa.JSON),
        sa.Column("urls", sa.JSON),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("simhash", sa.BigInteger),
        sa.Column("status", sa.Text),
    )
    op.create_index("uq_raw_posts_source_msg", "raw_posts", ["source_id", "tg_message_id"], unique=True)

    op.create_table(
        "topics",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("raw_post_id", sa.BigInteger, sa.ForeignKey("raw_posts.id"), nullable=False),
        sa.Column("ordinal", sa.Integer),
        sa.Column("text", sa.Text),
        sa.Column("urls", sa.JSON),
        sa.Column("status", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), server_onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_topics_raw_post_id", "topics", ["raw_post_id"])

    op.create_table(
        "summaries",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger, sa.ForeignKey("topics.id"), nullable=False),
        sa.Column("prompt_version", sa.Integer),
        sa.Column("model", sa.Text),
        sa.Column("summary_text", sa.Text),
        sa.Column("citations", sa.JSON),
        sa.Column("tokens_in", sa.Integer),
        sa.Column("tokens_out", sa.Integer),
        sa.Column("cost_cents", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_summaries_topic_id", "summaries", ["topic_id"])

    op.create_table(
        "digests",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("target_channel_id", sa.BigInteger),
        sa.Column("status", sa.Text),
    )
    op.create_index("ix_digests_scheduled_at", "digests", ["scheduled_at"])

    op.create_table(
        "digest_items",
        sa.Column("digest_id", sa.BigInteger, sa.ForeignKey("digests.id"), primary_key=True, nullable=False),
        sa.Column("summary_id", sa.BigInteger, sa.ForeignKey("summaries.id"), primary_key=True, nullable=False),
        sa.Column("position", sa.Integer),
    )


def downgrade() -> None:
    op.drop_table("digest_items")
    op.drop_index("ix_digests_scheduled_at", table_name="digests")
    op.drop_table("digests")
    op.drop_index("ix_summaries_topic_id", table_name="summaries")
    op.drop_table("summaries")
    op.drop_index("ix_topics_raw_post_id", table_name="topics")
    op.drop_table("topics")
    op.drop_index("uq_raw_posts_source_msg", table_name="raw_posts")
    op.drop_table("raw_posts")
    op.drop_table("sources")
    op.drop_table("master_sessions")
    op.drop_table("secrets")
    op.drop_table("settings")
