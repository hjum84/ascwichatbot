#!/usr/bin/env python3
"""
Migration: add disclaimer columns to chatbot_contents and create
the disclaimer_acceptances table.
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


def run():
    inspector = inspect(engine)
    with engine.begin() as connection:
        existing = {c["name"] for c in inspector.get_columns("chatbot_contents")}

        if "disclaimer_text" not in existing:
            print("Adding chatbot_contents.disclaimer_text ...")
            connection.execute(text(
                "ALTER TABLE chatbot_contents ADD COLUMN disclaimer_text TEXT"))
        else:
            print("disclaimer_text already exists")

        if "disclaimer_required" not in existing:
            print("Adding chatbot_contents.disclaimer_required ...")
            connection.execute(text(
                "ALTER TABLE chatbot_contents ADD COLUMN disclaimer_required BOOLEAN NOT NULL DEFAULT TRUE"))
        else:
            print("disclaimer_required already exists")

        if "disclaimer_version" not in existing:
            print("Adding chatbot_contents.disclaimer_version ...")
            connection.execute(text(
                "ALTER TABLE chatbot_contents ADD COLUMN disclaimer_version INTEGER NOT NULL DEFAULT 1"))
        else:
            print("disclaimer_version already exists")

        tables = inspector.get_table_names()
        if "disclaimer_acceptances" not in tables:
            print("Creating disclaimer_acceptances table ...")
            if engine.dialect.name == "sqlite":
                connection.execute(text("""
                    CREATE TABLE disclaimer_acceptances (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        user_email VARCHAR(255),
                        user_last_name VARCHAR(255),
                        chatbot_code VARCHAR(50),
                        program_name VARCHAR(100),
                        accepted_version INTEGER NOT NULL,
                        disclaimer_text_snapshot TEXT NOT NULL,
                        accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                connection.execute(text("""
                    CREATE TABLE disclaimer_acceptances (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER,
                        user_email VARCHAR(255),
                        user_last_name VARCHAR(255),
                        chatbot_code VARCHAR(50),
                        program_name VARCHAR(100),
                        accepted_version INTEGER NOT NULL,
                        disclaimer_text_snapshot TEXT NOT NULL,
                        accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            connection.execute(text(
                "CREATE INDEX ix_disc_accept_user ON disclaimer_acceptances (user_id)"))
            connection.execute(text(
                "CREATE INDEX ix_disc_accept_code ON disclaimer_acceptances (chatbot_code)"))
            connection.execute(text(
                "CREATE INDEX ix_disc_accept_at ON disclaimer_acceptances (accepted_at)"))
        else:
            print("disclaimer_acceptances already exists")

    print("Migration complete.")


if __name__ == "__main__":
    run()
