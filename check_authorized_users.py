#!/usr/bin/env python3
"""
Script to check the current state of authorized_users table
"""

import os
import sys
from datetime import datetime

# Add the project root to the path so we can import models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import get_db, close_db, AuthorizedUser

def check_authorized_users():
    """Check current authorized users in database"""
    try:
        print("🔍 Checking authorized_users table...")
        
        db = get_db()
        try:
            # Get all users
            all_users = db.query(AuthorizedUser).all()
            active_users = AuthorizedUser.get_all_active(db)
            
            print(f"📊 Total users in database: {len(all_users)}")
            print(f"📊 Active users in database: {len(active_users)}")
            
            if all_users:
                print("\n📋 Sample users:")
                for i, user in enumerate(all_users[:5]):
                    print(f"  {i+1}. {user.last_name} ({user.email}) - {user.status}")
                    print(f"      LO Root IDs: {user.lo_root_ids or 'None'}")
                
                if len(all_users) > 5:
                    print(f"  ... and {len(all_users) - 5} more users")
            else:
                print("❌ No users found in database")
                
        finally:
            close_db(db)
        
        return len(active_users) > 0
        
    except Exception as e:
        print(f"❌ Error checking database: {str(e)}")
        return False

def test_load_function():
    """Test the load_authorized_users function"""
    try:
        print("\n🧪 Testing load_authorized_users() function...")
        
        # Import the function
        from main import load_authorized_users
        
        authorized_users = load_authorized_users()
        
        print(f"📊 Function returned {len(authorized_users)} users")
        
        if authorized_users:
            print("✅ Function is working correctly")
            # Show sample
            sample_keys = list(authorized_users.keys())[:3]
            for key in sample_keys:
                user_data = authorized_users[key]
                print(f"  Sample: {key} → {user_data.get('last_name')} ({user_data.get('email')})")
        else:
            print("❌ Function returned empty result")
            
        return len(authorized_users) > 0
        
    except Exception as e:
        print(f"❌ Error testing function: {str(e)}")
        return False

if __name__ == "__main__":
    print("🔧 Checking Authorized Users Database Status")
    print(f"📅 Started at: {datetime.now()}")
    
    db_has_users = check_authorized_users()
    function_works = test_load_function()
    
    print(f"\n📋 Summary:")
    print(f"  Database has users: {'✅' if db_has_users else '❌'}")
    print(f"  Load function works: {'✅' if function_works else '❌'}")
    
    if not db_has_users:
        print("\n💡 Next steps:")
        print("1. Upload CSV file via admin panel")
        print("2. Check for any error messages in the upload process")
        print("3. Verify CSV format matches requirements")
    
    print(f"📅 Finished at: {datetime.now()}") 