"""add users.tz_confirmed

Revision ID: 4b1e8a2c7f3d
Revises: 93e39126d9d6
Create Date: 2026-09-25 19:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b1e8a2c7f3d"
down_revision: str | Sequence[str] | None = "93e39126d9d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("tz_confirmed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    # Уже зарегистрированные пользователи пояс фактически выбрали —
    # считаем подтверждённым, чтобы не гнать их через онбординг заново.
    op.execute(sa.text("UPDATE users SET tz_confirmed = true"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "tz_confirmed")
