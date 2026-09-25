"""add users.help_shown

Revision ID: 9c2d5e7a1b4f
Revises: 4b1e8a2c7f3d
Create Date: 2026-09-25 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c2d5e7a1b4f"
down_revision: str | Sequence[str] | None = "4b1e8a2c7f3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("help_shown", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "help_shown")
