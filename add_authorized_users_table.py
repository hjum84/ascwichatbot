#!/usr/bin/env python3
"""
Migration script to add the authorized_users table
Run this once to create the new table structure
"""

import os
import sys
from datetime import datetime

# Add the project root to the path so we can import models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import Base, engine, get_db, close_db, AuthorizedUser
from sqlalchemy import text

def create_authorized_users_table():
    """Create the authorized_users table"""
    try:
        print("🚀 Creating authorized_users table...")
        
        # Create the table
        Base.metadata.create_all(bind=engine)
        
        # Verify table was created
        db = get_db()
        try:
            # Test if table exists by querying it
            result = db.execute(text("SELECT COUNT(*) FROM authorized_users"))
            count = result.scalar()
            print(f"✅ Table created successfully! Current records: {count}")
            
        finally:
            close_db(db)
        
        print("✅ Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error creating table: {str(e)}")
        return False

if __name__ == "__main__":
    print("🔧 Starting migration: Add authorized_users table")
    print(f"📅 Started at: {datetime.now()}")
    
    success = create_authorized_users_table()
    
    if success:
        print("🎉 Migration completed successfully!")
        print("\n📋 Next steps:")
        print("1. Upload your CSV file via admin panel")
        print("2. The data will be stored in the database instead of CSV files")
        print("3. Registration will work consistently across deployments")
    else:
        print("💥 Migration failed! Please check the error messages above.")
    
    print(f"📅 Finished at: {datetime.now()}") 