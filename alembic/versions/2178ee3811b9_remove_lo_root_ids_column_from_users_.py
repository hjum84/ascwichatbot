"""remove lo_root_ids column from users table

Revision ID: 2178ee3811b9
Revises: 635f2ccc0f5b
Create Date: 2025-05-27 22:21:17.067491

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2178ee3811b9'
down_revision: Union[str, None] = '635f2ccc0f5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
