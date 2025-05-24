"""add_user_management_and_lo_root_id_tables

Revision ID: 227e80a0ea44
Revises: b70190e2b3b8
Create Date: 2025-05-23 21:20:42.293347

"""
from typing import Sequence, Union
from datetime import datetime, timedelta

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '227e80a0ea44'
down_revision: Union[str, None] = 'b70190e2b3b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('status', sa.String(), nullable=False, server_default='Inactive'))
    op.add_column('users', sa.Column('date_added', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))
    op.add_column('users', sa.Column('expiry_date', sa.DateTime(), nullable=True))
    
    op.create_table('user_lo_root_ids',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('lo_root_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('user_id', 'lo_root_id')
    )
    
    op.create_table('chatbot_lo_root_association',
        sa.Column('chatbot_id', sa.Integer(), nullable=False),
        sa.Column('lo_root_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['chatbot_id'], ['chatbot_contents.id'], ),
        sa.PrimaryKeyConstraint('chatbot_id', 'lo_root_id')
    )
    
    op.drop_column('users', 'current_program')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('current_program', sa.String(), nullable=True, server_default='BCC'))
    
    op.drop_table('chatbot_lo_root_association')
    
    op.drop_table('user_lo_root_ids')
    
    op.drop_column('users', 'expiry_date')
    op.drop_column('users', 'date_added')
    op.drop_column('users', 'status')
