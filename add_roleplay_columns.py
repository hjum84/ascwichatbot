#!/usr/bin/env python3
"""
Migration script: add role-play session tracking columns to chat_history.

Adds:
1) roleplay_session_id (VARCHAR(64), nullable, indexed)
2) roleplay_state (VARCHAR(16), nullable)

Both columns are nullable, so existing rows are untouched and all existing
queries continue to work unchanged. Run once against the active database
(Neon) before deploying the main.py version that uses these columns:

    python add_roleplay_columns.py
"""

import os
from sqlalchemy import create_engine, inspect, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable is not set.")
    raise SystemExit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def add_roleplay_columns():
    inspector = inspect(engine)
    with engine.begin() as connection:
        existing = {col["name"] for col in inspector.get_columns("chat_history")}

        if "roleplay_session_id" not in existing:
            print("Adding chat_history.roleplay_session_id ...")
            connection.execute(
                text("ALTER TABLE chat_history ADD COLUMN roleplay_session_id VARCHAR(64)")
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_chat_history_roleplay_session_id "
                    "ON chat_history (roleplay_session_id)"
                )
            )
            print("Added roleplay_session_id (with index)")
        else:
            print("roleplay_session_id already exists")

        if "roleplay_state" not in existing:
            print("Adding chat_history.roleplay_state ...")
            connection.execute(
                text("ALTER TABLE chat_history ADD COLUMN roleplay_state VARCHAR(16)")
            )
            print("Added roleplay_state")
        else:
            print("roleplay_state already exists")

    print("Migration complete.")


if __name__ == "__main__":
    add_roleplay_columns()
