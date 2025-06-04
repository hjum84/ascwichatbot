"""Add password_hash field to users table

Revision ID: a7baf7b52083
Revises: 2178ee3811b9
Create Date: 2025-06-03 19:01:34.042867

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7baf7b52083'
down_revision: Union[str, None] = '2178ee3811b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add password_hash column to users table
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove password_hash column from users table
    op.drop_column('users', 'password_hash')
