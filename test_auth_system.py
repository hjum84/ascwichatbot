#!/usr/bin/env python3
"""
Comprehensive test script for the authentication system
"""

import os
import sys
import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path to import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import User, SessionLocal, get_db, close_db
from sqlalchemy import text

def test_database_schema():
    """Test if required columns exist in users table"""
    print("=" * 50)
    print("1. Testing Database Schema")
    print("=" * 50)
    
    db = get_db()
    try:
        # Check if email column exists
        result = db.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name IN ('email', 'password_hash', 'visit_count')
            ORDER BY column_name
        """))
        
        columns = result.fetchall()
        
        required_columns = {'email', 'password_hash', 'visit_count'}
        found_columns = {col[0] for col in columns}
        
        print(f"Found columns: {found_columns}")
        print(f"Required columns: {required_columns}")
        
        if required_columns.issubset(found_columns):
            print("✅ All required columns exist!")
            for col in columns:
                print(f"   - {col[0]}: {col[1]} (nullable: {col[2]})")
        else:
            missing = required_columns - found_columns
            print(f"❌ Missing columns: {missing}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Error checking database schema: {e}")
        return False
    finally:
        close_db(db)

def test_user_model():
    """Test User model password functionality"""
    print("\n" + "=" * 50)
    print("2. Testing User Model Password Methods")
    print("=" * 50)
    
    db = get_db()
    try:
        # Test password setting and checking
        test_email = "test_user@example.com"
        test_password = "secure_password_123"
        
        # Clean up any existing test user
        existing_user = User.get_by_email(db, test_email)
        if existing_user:
            db.delete(existing_user)
            db.commit()
        
        # Create a test user
        test_user = User(
            last_name="TestUser",
            email=test_email,
            status="Active"
        )
        
        # Test password methods
        print(f"Testing with password: {test_password}")
        
        # Test has_password() before setting password
        print(f"has_password() before setting: {test_user.has_password()}")
        if test_user.has_password():
            print("❌ has_password() should return False before password is set")
            return False
        else:
            print("✅ has_password() correctly returns False before password is set")
        
        # Set password
        test_user.set_password(test_password)
        print(f"Password hash created: {test_user.password_hash[:20]}...")
        
        # Test has_password() after setting password
        print(f"has_password() after setting: {test_user.has_password()}")
        if not test_user.has_password():
            print("❌ has_password() should return True after password is set")
            return False
        else:
            print("✅ has_password() correctly returns True after password is set")
        
        # Test password verification
        if test_user.check_password(test_password):
            print("✅ Password verification successful with correct password")
        else:
            print("❌ Password verification failed with correct password")
            return False
        
        # Test wrong password
        if not test_user.check_password("wrong_password"):
            print("✅ Password verification correctly failed with wrong password")
        else:
            print("❌ Password verification should fail with wrong password")
            return False
        
        # Test password hash uniqueness (same password should generate different hashes)
        test_user2 = User(
            last_name="TestUser2",
            email="test_user2@example.com",
            status="Active"
        )
        test_user2.set_password(test_password)
        
        if test_user.password_hash != test_user2.password_hash:
            print("✅ Same password generates unique hashes (salt working)")
        else:
            print("❌ Same password generated identical hashes (salt not working)")
            return False
        
        # Clean up
        if existing_user:
            db.delete(existing_user)
        db.commit()
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing user model: {e}")
        db.rollback()
        return False
    finally:
        close_db(db)

def test_user_queries():
    """Test User model query methods"""
    print("\n" + "=" * 50)
    print("3. Testing User Model Query Methods")
    print("=" * 50)
    
    db = get_db()
    try:
        # Test get_by_email method
        print("Testing get_by_email method...")
        
        # Should return None for non-existent email
        non_existent = User.get_by_email(db, "nonexistent@example.com")
        if non_existent is None:
            print("✅ get_by_email returns None for non-existent email")
        else:
            print("❌ get_by_email should return None for non-existent email")
            return False
        
        # Test with existing users (if any)
        existing_users = db.query(User).limit(1).all()
        if existing_users:
            test_user = existing_users[0]
            found_user = User.get_by_email(db, test_user.email)
            if found_user and found_user.id == test_user.id:
                print(f"✅ get_by_email successfully found user: {found_user.email}")
            else:
                print("❌ get_by_email failed to find existing user")
                return False
        else:
            print("ℹ️  No existing users to test get_by_email with")
        
        # Test get_by_credentials method
        print("Testing get_by_credentials method...")
        if existing_users:
            test_user = existing_users[0]
            found_user = User.get_by_credentials(db, test_user.last_name, test_user.email)
            if found_user and found_user.id == test_user.id:
                print(f"✅ get_by_credentials successfully found user: {found_user.last_name}, {found_user.email}")
            else:
                print("❌ get_by_credentials failed to find existing user")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing user queries: {e}")
        return False
    finally:
        close_db(db)

def test_database_connection():
    """Test basic database connectivity"""
    print("\n" + "=" * 50)
    print("4. Testing Database Connection")
    print("=" * 50)
    
    try:
        db = get_db()
        
        # Test basic query
        result = db.execute(text("SELECT COUNT(*) FROM users"))
        user_count = result.scalar()
        
        print(f"✅ Database connection successful")
        print(f"✅ Total users in database: {user_count}")
        
        close_db(db)
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def test_environment_variables():
    """Test if required environment variables are set"""
    print("\n" + "=" * 50)
    print("5. Testing Environment Variables")
    print("=" * 50)
    
    required_vars = [
        'DATABASE_URL',
        'SECRET_KEY',
        'MAIL_SERVER',
        'MAIL_PORT',
        'MAIL_USERNAME',
        'MAIL_PASSWORD'
    ]
    
    missing_vars = []
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            if var in ['DATABASE_URL', 'SECRET_KEY', 'MAIL_PASSWORD']:
                print(f"✅ {var}: {'*' * min(10, len(value))}... (hidden)")
            else:
                print(f"✅ {var}: {value}")
        else:
            print(f"❌ {var}: Not set")
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\n❌ Missing environment variables: {missing_vars}")
        return False
    else:
        print(f"\n✅ All required environment variables are set")
        return True

def main():
    """Run all tests"""
    print("🧪 Authentication System Test Suite")
    print("=" * 80)
    
    tests = [
        ("Environment Variables", test_environment_variables),
        ("Database Connection", test_database_connection),
        ("Database Schema", test_database_schema),
        ("User Model", test_user_model),
        ("User Queries", test_user_queries),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🔄 Running {test_name} test...")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:<10} {test_name}")
        if result:
            passed += 1
    
    print("-" * 80)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Authentication system is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 