"""add display_name to chatbot_contents

Revision ID: 635f2ccc0f5b
Revises: 227e80a0ea44
Create Date: 2025-05-27 22:16:12.916476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '635f2ccc0f5b'
down_revision: Union[str, None] = '227e80a0ea44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
