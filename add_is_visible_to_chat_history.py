from models import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text('ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS is_visible BOOLEAN NOT NULL DEFAULT TRUE'))
    conn.commit()
print('is_visible column added to chat_history (if it did not exist)') 