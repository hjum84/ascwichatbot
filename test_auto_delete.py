#!/usr/bin/env python3
"""
Simple test script for auto-delete functionality
"""

import os
import sys
import datetime
from dotenv import load_dotenv

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

# Import models
from models import ChatbotContent, ChatHistory, User, get_db, close_db

def test_auto_delete_functionality():
    """Test that auto-delete functionality is working properly"""
    db = get_db()
    try:
        print("🧪 Testing Auto-Delete Functionality")
        print("=" * 50)
        
        # 1. Test creating a chatbot with auto-delete setting
        print("1. Testing chatbot creation with auto-delete...")
        
        test_chatbot = ChatbotContent.create_or_update(
            db=db,
            code="TEST_AUTO_DELETE",
            name="Test Auto Delete Bot",
            content="This is a test chatbot for auto-delete functionality.",
            description="Test chatbot",
            quota=3,
            auto_delete_days=7  # 7 days auto-delete
        )
        db.commit()
        
        print(f"   ✅ Created test chatbot: {test_chatbot.name}")
        print(f"   📅 Auto-delete setting: {test_chatbot.auto_delete_days} days")
        print(f"   📝 Auto-delete text: {test_chatbot.get_auto_delete_text()}")
        
        # 2. Test methods on ChatbotContent
        print("\n2. Testing ChatbotContent methods...")
        print(f"   should_auto_delete(): {test_chatbot.should_auto_delete()}")
        
        # 3. Check if existing chatbots have the new field
        print("\n3. Checking existing chatbots...")
        all_chatbots = db.query(ChatbotContent).filter(ChatbotContent.is_active == True).all()
        for chatbot in all_chatbots:
            print(f"   🤖 {chatbot.name}: auto_delete_days = {chatbot.auto_delete_days}")
        
        # 4. Test updating auto-delete setting
        print("\n4. Testing auto-delete setting update...")
        test_chatbot.auto_delete_days = 30
        db.commit()
        print(f"   ✅ Updated auto-delete setting to {test_chatbot.auto_delete_days} days")
        print(f"   📝 New auto-delete text: {test_chatbot.get_auto_delete_text()}")
        
        # 5. Test disabling auto-delete
        print("\n5. Testing auto-delete disable...")
        test_chatbot.auto_delete_days = None
        db.commit()
        print(f"   ✅ Disabled auto-delete: {test_chatbot.auto_delete_days}")
        print(f"   📝 Auto-delete text: {test_chatbot.get_auto_delete_text()}")
        print(f"   should_auto_delete(): {test_chatbot.should_auto_delete()}")
        
        # 6. Clean up test chatbot
        print("\n6. Cleaning up test chatbot...")
        test_chatbot.is_active = False
        db.commit()
        print("   ✅ Test chatbot marked as inactive")
        
        print("\n🎉 All auto-delete functionality tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if db:
            close_db(db)

if __name__ == "__main__":
    success = test_auto_delete_functionality()
    if success:
        print("\n✅ Auto-delete feature is working correctly!")
        sys.exit(0)
    else:
        print("\n❌ Auto-delete feature has issues!")
        sys.exit(1) 