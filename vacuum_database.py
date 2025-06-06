import psycopg2
import os
from urllib.parse import urlparse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_database_url():
    """Get database URL from environment variables only"""
    # SECURITY: Only use environment variables for database connection
    url = os.environ.get('DATABASE_URL')
    if url:
        return url
    
    # Never hardcode database credentials for security reasons
    logger.error("❌ DATABASE_URL not found in environment variables")
    logger.error("💡 Please set DATABASE_URL environment variable")
    return None

def vacuum_database():
    """Perform VACUUM to reclaim disk space"""
    database_url = get_database_url()
    
    if not database_url:
        print("❌ DATABASE_URL not found")
        return False
    
    try:
        # Parse the database URL
        parsed = urlparse(database_url)
        
        # Connect directly with psycopg2 (needed for VACUUM)
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port,
            database=parsed.path[1:],  # Remove leading '/'
            user=parsed.username,
            password=parsed.password
        )
        
        # Set autocommit (required for VACUUM)
        conn.autocommit = True
        cursor = conn.cursor()
        
        print("🔍 BEFORE VACUUM:")
        
        # Check table size before
        cursor.execute("""
            SELECT 
                pg_size_pretty(pg_total_relation_size('authorized_users')) as table_size,
                pg_size_pretty(pg_database_size(current_database())) as db_size
        """)
        before_sizes = cursor.fetchone()
        print(f"   Table size: {before_sizes[0]}")
        print(f"   Database size: {before_sizes[1]}")
        
        # Check for dead tuples
        cursor.execute("""
            SELECT 
                schemaname,
                relname,
                n_tup_ins,
                n_tup_upd,
                n_tup_del,
                n_dead_tup
            FROM pg_stat_user_tables 
            WHERE relname = 'authorized_users'
        """)
        stats = cursor.fetchone()
        if stats:
            print(f"   Dead tuples: {stats[5]:,}")
            print(f"   Inserted: {stats[2]:,}, Updated: {stats[3]:,}, Deleted: {stats[4]:,}")
        
        print(f"\n🚀 PERFORMING VACUUM...")
        
        # Perform VACUUM FULL on the specific table
        print("   Running VACUUM FULL on authorized_users table...")
        cursor.execute("VACUUM FULL authorized_users")
        
        # Also vacuum the entire database
        print("   Running VACUUM on entire database...")
        cursor.execute("VACUUM")
        
        print(f"\n🔍 AFTER VACUUM:")
        
        # Check table size after
        cursor.execute("""
            SELECT 
                pg_size_pretty(pg_total_relation_size('authorized_users')) as table_size,
                pg_size_pretty(pg_database_size(current_database())) as db_size
        """)
        after_sizes = cursor.fetchone()
        print(f"   Table size: {after_sizes[0]}")
        print(f"   Database size: {after_sizes[1]}")
        
        # Check dead tuples after
        cursor.execute("""
            SELECT 
                n_dead_tup
            FROM pg_stat_user_tables 
            WHERE relname = 'authorized_users'
        """)
        dead_tuples_after = cursor.fetchone()
        if dead_tuples_after:
            print(f"   Dead tuples after: {dead_tuples_after[0]:,}")
        
        print(f"\n✅ VACUUM COMPLETED!")
        print(f"   Before: {before_sizes[1]} → After: {after_sizes[1]}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error during VACUUM: {str(e)}")
        return False

def main():
    """Main execution"""
    print("🧹 VACUUMING DATABASE TO RECLAIM DISK SPACE")
    print("=" * 50)
    
    success = vacuum_database()
    
    if success:
        print("\n🎉 Database optimization completed!")
        print("💡 Database size should now be reduced to proper levels")
    else:
        print("\n❌ Database optimization failed")
        print("💡 You may need to manually run VACUUM FULL in production")

if __name__ == "__main__":
    main() 