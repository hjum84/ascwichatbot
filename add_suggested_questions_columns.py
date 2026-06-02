#!/usr/bin/env python3
"""
Migration: add suggested question settings to chatbot_contents.
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

        if "suggested_questions_json" not in existing:
            print("Adding chatbot_contents.suggested_questions_json ...")
            connection.execute(text(
                "ALTER TABLE chatbot_contents ADD COLUMN suggested_questions_json TEXT"))
        else:
            print("suggested_questions_json already exists")

        if "suggested_questions_count" not in existing:
            print("Adding chatbot_contents.suggested_questions_count ...")
            connection.execute(text(
                "ALTER TABLE chatbot_contents ADD COLUMN suggested_questions_count INTEGER NOT NULL DEFAULT 3"))
        else:
            print("suggested_questions_count already exists")

    print("Migration complete.")


if __name__ == "__main__":
    run()
