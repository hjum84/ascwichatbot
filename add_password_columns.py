#!/usr/bin/env python3
"""
Script to manually add email, password_hash, and visit_count columns to users table
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable is not set.")
    exit(1)

engine = create_engine(DATABASE_URL)

def add_missing_columns():
    """Add missing columns to users table"""
    with engine.connect() as connection:
        try:
            # Check if email column exists
            result = connection.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'email'
            """))
            
            email_exists = result.fetchone() is not None
            
            if not email_exists:
                print("Adding email column to users table...")
                connection.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN email VARCHAR UNIQUE
                """))
                print("✓ Email column added successfully")
            else:
                print("✓ Email column already exists")
            
            # Check if password_hash column exists
            result = connection.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'password_hash'
            """))
            
            password_hash_exists = result.fetchone() is not None
            
            if not password_hash_exists:
                print("Adding password_hash column to users table...")
                connection.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN password_hash VARCHAR(255)
                """))
                print("✓ Password_hash column added successfully")
            else:
                print("✓ Password_hash column already exists")
            
            # Check if visit_count column exists
            result = connection.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'visit_count'
            """))
            
            visit_count_exists = result.fetchone() is not None
            
            if not visit_count_exists:
                print("Adding visit_count column to users table...")
                connection.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN visit_count INTEGER DEFAULT 0
                """))
                print("✓ Visit_count column added successfully")
            else:
                print("✓ Visit_count column already exists")
            
            # Commit the changes
            connection.commit()
            print("\n✓ All missing columns have been added to the users table")
            
        except Exception as e:
            print(f"Error adding columns: {e}")
            connection.rollback()
            raise e

if __name__ == "__main__":
    print("Adding missing columns to users table...")
    add_missing_columns()
    print("✓ Database schema update completed!") 