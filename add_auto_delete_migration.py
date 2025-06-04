#!/usr/bin/env python3
"""
Migration script to add auto-delete functionality columns
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import datetime

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable is not set.")
    exit(1)

engine = create_engine(DATABASE_URL)

def backup_reminder():
    """Remind admin to backup database"""
    print("=" * 60)
    print("🚨 IMPORTANT: DATABASE MIGRATION")
    print("=" * 60)
    print("This script will add new columns for auto-delete functionality:")
    print("1. chatbot_contents.auto_delete_days (INTEGER, nullable)")
    print("2. chat_history.deletion_notified_at (TIMESTAMP, nullable)")
    print()
    print("⚠️  STRONGLY RECOMMENDED: Backup your database first!")
    print("   Command: pg_dump your_database > backup_$(date +%Y%m%d_%H%M%S).sql")
    print()
    
    response = input("Continue with migration? (yes/no): ").lower().strip()
    if response not in ['yes', 'y']:
        print("Migration cancelled.")
        exit(0)

def add_auto_delete_columns():
    """Add auto-delete related columns to existing tables"""
    with engine.connect() as connection:
        try:
            print(f"🔧 Starting migration at {datetime.datetime.now()}")
            
            # Check if auto_delete_days column exists in chatbot_contents
            result = connection.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'chatbot_contents' AND column_name = 'auto_delete_days'
            """))
            
            auto_delete_exists = result.fetchone() is not None
            
            if not auto_delete_exists:
                print("📝 Adding auto_delete_days column to chatbot_contents table...")
                connection.execute(text("""
                    ALTER TABLE chatbot_contents 
                    ADD COLUMN auto_delete_days INTEGER DEFAULT NULL
                """))
                print("✅ auto_delete_days column added successfully")
            else:
                print("✅ auto_delete_days column already exists")
            
            # Check if deletion_notified_at column exists in chat_history
            result = connection.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'chat_history' AND column_name = 'deletion_notified_at'
            """))
            
            notification_exists = result.fetchone() is not None
            
            if not notification_exists:
                print("📝 Adding deletion_notified_at column to chat_history table...")
                connection.execute(text("""
                    ALTER TABLE chat_history 
                    ADD COLUMN deletion_notified_at TIMESTAMP DEFAULT NULL
                """))
                print("✅ deletion_notified_at column added successfully")
            else:
                print("✅ deletion_notified_at column already exists")
            
            # Commit the changes
            connection.commit()
            print()
            print("🎉 Migration completed successfully!")
            print("✅ All auto-delete columns have been added")
            print(f"✅ Migration finished at {datetime.datetime.now()}")
            
            # Verify columns exist
            print("\n🔍 Verifying migration...")
            result = connection.execute(text("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name IN ('chatbot_contents', 'chat_history')
                AND column_name IN ('auto_delete_days', 'deletion_notified_at')
                ORDER BY table_name, column_name
            """))
            
            columns = result.fetchall()
            for col in columns:
                print(f"   ✓ {col[0]} ({col[1]}, nullable: {col[2]})")
            
        except Exception as e:
            print(f"❌ Error during migration: {e}")
            connection.rollback()
            raise e

def show_rollback_info():
    """Show how to rollback if needed"""
    print("\n" + "=" * 60)
    print("📋 ROLLBACK INFORMATION")
    print("=" * 60)
    print("If you need to rollback this migration, run:")
    print("ALTER TABLE chatbot_contents DROP COLUMN IF EXISTS auto_delete_days;")
    print("ALTER TABLE chat_history DROP COLUMN IF EXISTS deletion_notified_at;")
    print("=" * 60)

if __name__ == "__main__":
    backup_reminder()
    add_auto_delete_columns()
    show_rollback_info()
    print("\n✅ Migration script completed successfully!")
    print("🔄 Next step: Update models.py to include the new fields") 