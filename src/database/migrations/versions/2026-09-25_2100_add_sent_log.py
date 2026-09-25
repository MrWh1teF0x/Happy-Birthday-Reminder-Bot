"""add sent_notifications_log

Revision ID: 2e6b9d4a8c1e
Revises: 9c2d5e7a1b4f
Create Date: 2026-09-25 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e6b9d4a8c1e"
down_revision: str | Sequence[str] | None = "9c2d5e7a1b4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "sent_notifications_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("setting_id", sa.Integer(), nullable=False),
        sa.Column("notify_date", sa.Date(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["persons.id"],
            name=op.f("fk_sent_notifications_log_person_id_persons"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["setting_id"],
            ["user_settings.id"],
            name=op.f("fk_sent_notifications_log_setting_id_user_settings"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tg_id"],
            ["users.tg_id"],
            name=op.f("fk_sent_notifications_log_tg_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sent_notifications_log")),
        sa.UniqueConstraint(
            "tg_id", "person_id", "setting_id", "notify_date", name="uq_sent_notification"
        ),
    )
    op.create_index(
        op.f("ix_sent_notifications_log_tg_id"), "sent_notifications_log", ["tg_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_sent_notifications_log_tg_id"), table_name="sent_notifications_log")
    op.drop_table("sent_notifications_log")
