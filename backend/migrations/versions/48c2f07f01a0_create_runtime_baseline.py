"""Базовая runtime-миграция.

Revision ID: 48c2f07f01a0
Revises:
Create Date: 2026-08-31
"""

from collections.abc import Sequence

revision: str = "48c2f07f01a0"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Применить базовую runtime-миграцию."""
    pass


def downgrade() -> None:
    """Откатить базовую runtime-миграцию."""
    pass
