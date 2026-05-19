"""Add chatbot_mode and ai_model fields to ChatbotContent

Revision ID: c1a4f9d72e10
Revises: a7baf7b52083
Create Date: 2026-05-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a4f9d72e10'
down_revision: Union[str, None] = 'a7baf7b52083'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Adds two columns to ``chatbot_contents`` to support per-chatbot
    conversation behavior and model selection:

    * ``chatbot_mode`` - 'knowledge_retrieval' (default, stateless Q&A)
      or 'critical_thinking_agent' (multi-turn dialogue using history).
    * ``ai_model`` - configurable model name (e.g. 'gemini-2.5-flash').

    Both columns are populated for existing rows via ``server_default``
    so that current behavior is preserved.
    """
    op.add_column(
        'chatbot_contents',
        sa.Column(
            'chatbot_mode',
            sa.String(length=50),
            nullable=False,
            server_default='knowledge_retrieval',
        ),
    )
    op.add_column(
        'chatbot_contents',
        sa.Column(
            'ai_model',
            sa.String(length=100),
            nullable=False,
            server_default='gemini-2.5-flash',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chatbot_contents', 'ai_model')
    op.drop_column('chatbot_contents', 'chatbot_mode')
