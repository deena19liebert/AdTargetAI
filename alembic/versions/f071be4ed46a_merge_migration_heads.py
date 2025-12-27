"""Merge migration heads

Revision ID: f071be4ed46a
Revises: 09c235a5a95b, ca5315e446bb
Create Date: 2025-12-26 20:52:02.794992

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f071be4ed46a'
down_revision: Union[str, Sequence[str], None] = ('09c235a5a95b', 'ca5315e446bb')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
