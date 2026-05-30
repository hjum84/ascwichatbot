#!/usr/bin/env python3
"""
Migration script: add guardrail analytics columns to chat_history.

Adds:
1) guardrail_tier (VARCHAR(32), nullable)
2) guardrail_rule_name (VARCHAR(255), nullable)
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


def add_guardrail_columns():
    inspector = inspect(engine)
    with engine.begin() as connection:
        existing = {col["name"] for col in inspector.get_columns("chat_history")}

        if "guardrail_tier" not in existing:
            print("Adding chat_history.guardrail_tier ...")
            connection.execute(
                text("ALTER TABLE chat_history ADD COLUMN guardrail_tier VARCHAR(32)")
            )
            print("Added guardrail_tier")
        else:
            print("guardrail_tier already exists")

        if "guardrail_rule_name" not in existing:
            print("Adding chat_history.guardrail_rule_name ...")
            connection.execute(
                text("ALTER TABLE chat_history ADD COLUMN guardrail_rule_name VARCHAR(255)")
            )
            print("Added guardrail_rule_name")
        else:
            print("guardrail_rule_name already exists")

    print("Migration complete.")


if __name__ == "__main__":
    add_guardrail_columns()
