import psycopg2
import os
from urllib.parse import urlparse
import logging
from datetime import datetime, timedelta
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_database_url():
    """Get database URL from environment variables"""
    url = os.environ.get('DATABASE_URL')
    if url:
        return url
    
    # Try local .env file
    try:
        with open('.env', 'r') as f:
            for line in f:
                if line.startswith('DATABASE_URL='):
                    return line.split('=', 1)[1].strip()
    except FileNotFoundError:
        pass
    
    logger.error("❌ DATABASE_URL not found in environment variables or .env file")
    return None

def check_database_security():
    """Comprehensive database security check"""
    database_url = get_database_url()
    
    if not database_url:
        print("❌ DATABASE_URL not found")
        return False
    
    try:
        # Parse the database URL
        parsed = urlparse(database_url)
        
        # Connect to database
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port,
            database=parsed.path[1:],  # Remove leading '/'
            user=parsed.username,
            password=parsed.password
        )
        
        cursor = conn.cursor()
        
        print("🔍 DATABASE SECURITY AUDIT")
        print("=" * 50)
        print(f"📅 Audit Time: {datetime.now()}")
        print(f"🏢 Database: {parsed.path[1:]}")
        print(f"🖥️  Host: {parsed.hostname}")
        print()
        
        # 1. Check current active connections
        print("1️⃣ CURRENT ACTIVE CONNECTIONS:")
        print("-" * 30)
        cursor.execute("""
            SELECT 
                pid,
                usename,
                application_name,
                client_addr,
                client_hostname,
                client_port,
                backend_start,
                state,
                state_change,
                query_start,
                EXTRACT(EPOCH FROM (now() - backend_start)) as connection_duration_seconds
            FROM pg_stat_activity 
            WHERE state != 'idle'
            ORDER BY backend_start DESC
        """)
        
        active_connections = cursor.fetchall()
        if active_connections:
            for conn_info in active_connections:
                pid, user, app, client_ip, hostname, port, start, state, state_change, query_start, duration = conn_info
                print(f"   🔗 PID: {pid}")
                print(f"      👤 User: {user}")
                print(f"      📱 App: {app or 'Unknown'}")
                print(f"      🌐 Client: {client_ip or 'local'}")
                print(f"      🏠 Hostname: {hostname or 'Unknown'}")
                print(f"      ⏰ Connected: {start}")
                print(f"      📊 State: {state}")
                print(f"      ⏱️  Duration: {duration:.0f} seconds")
                print()
        else:
            print("   ✅ No active connections (besides this audit)")
            print()
        
        # 2. Check database statistics
        print("2️⃣ DATABASE CONNECTION STATISTICS:")
        print("-" * 35)
        cursor.execute("""
            SELECT 
                datname,
                numbackends,
                xact_commit,
                xact_rollback,
                blks_read,
                blks_hit,
                tup_returned,
                tup_fetched,
                tup_inserted,
                tup_updated,
                tup_deleted,
                conflicts,
                temp_files,
                temp_bytes,
                deadlocks,
                stats_reset
            FROM pg_stat_database 
            WHERE datname = current_database()
        """)
        
        db_stats = cursor.fetchone()
        if db_stats:
            print(f"   📊 Current Backends: {db_stats[1]}")
            print(f"   ✅ Commits: {db_stats[2]:,}")
            print(f"   ❌ Rollbacks: {db_stats[3]:,}")
            print(f"   📖 Blocks Read: {db_stats[4]:,}")
            print(f"   🎯 Cache Hits: {db_stats[5]:,}")
            print(f"   📥 Tuples Fetched: {db_stats[7]:,}")
            print(f"   ➕ Inserts: {db_stats[8]:,}")
            print(f"   ✏️  Updates: {db_stats[9]:,}")
            print(f"   🗑️  Deletes: {db_stats[10]:,}")
            print(f"   ⚡ Conflicts: {db_stats[11]:,}")
            print(f"   🔒 Deadlocks: {db_stats[14]:,}")
            print(f"   🔄 Stats Reset: {db_stats[15]}")
            print()
        
        # 3. Check for suspicious activity patterns
        print("3️⃣ SUSPICIOUS ACTIVITY ANALYSIS:")
        print("-" * 33)
        
        # Check for multiple connections from same IP
        cursor.execute("""
            SELECT 
                client_addr,
                COUNT(*) as connection_count,
                array_agg(DISTINCT usename) as users,
                array_agg(DISTINCT application_name) as applications
            FROM pg_stat_activity 
            WHERE client_addr IS NOT NULL
            GROUP BY client_addr
            HAVING COUNT(*) > 1
        """)
        
        suspicious_ips = cursor.fetchall()
        if suspicious_ips:
            print("   ⚠️ Multiple connections from same IP:")
            for ip_info in suspicious_ips:
                ip, count, users, apps = ip_info
                print(f"      🌐 IP: {ip}")
                print(f"      🔢 Connections: {count}")
                print(f"      👥 Users: {users}")
                print(f"      📱 Apps: {apps}")
                print()
        else:
            print("   ✅ No suspicious multiple connections detected")
            print()
        
        # 4. Check user activity
        print("4️⃣ USER ACTIVITY SUMMARY:")
        print("-" * 25)
        cursor.execute("""
            SELECT 
                usename,
                COUNT(*) as active_connections,
                MIN(backend_start) as first_connection,
                MAX(backend_start) as latest_connection
            FROM pg_stat_activity 
            GROUP BY usename
            ORDER BY active_connections DESC
        """)
        
        user_activity = cursor.fetchall()
        for user_info in user_activity:
            user, connections, first, latest = user_info
            print(f"   👤 User: {user}")
            print(f"      🔗 Active Connections: {connections}")
            print(f"      🕐 First Connected: {first}")
            print(f"      🕕 Latest Connected: {latest}")
            print()
        
        # 5. Check database size and recent changes
        print("5️⃣ DATABASE SIZE & RECENT ACTIVITY:")
        print("-" * 35)
        cursor.execute("""
            SELECT 
                pg_size_pretty(pg_database_size(current_database())) as db_size,
                (SELECT COUNT(*) FROM authorized_users) as total_users,
                (SELECT COUNT(*) FROM chat_history) as total_chats,
                (SELECT COUNT(*) FROM users) as registered_users
        """)
        
        size_info = cursor.fetchone()
        if size_info:
            print(f"   💾 Database Size: {size_info[0]}")
            print(f"   👥 Authorized Users: {size_info[1]:,}")
            print(f"   💬 Chat Records: {size_info[2]:,}")
            print(f"   📝 Registered Users: {size_info[3]:,}")
            print()
        
        # 6. Check for recent heavy operations
        print("6️⃣ RECENT HEAVY OPERATIONS:")
        print("-" * 27)
        cursor.execute("""
            SELECT 
                schemaname,
                tablename,
                n_tup_ins,
                n_tup_upd,
                n_tup_del,
                n_dead_tup,
                last_vacuum,
                last_autovacuum,
                last_analyze,
                last_autoanalyze
            FROM pg_stat_user_tables 
            WHERE n_tup_ins > 0 OR n_tup_upd > 0 OR n_tup_del > 0
            ORDER BY (n_tup_ins + n_tup_upd + n_tup_del) DESC
        """)
        
        table_activity = cursor.fetchall()
        for table_info in table_activity:
            schema, table, inserts, updates, deletes, dead, vac, autovac, analyze, autoanalyze = table_info
            total_ops = inserts + updates + deletes
            print(f"   📋 Table: {schema}.{table}")
            print(f"      ➕ Inserts: {inserts:,}")
            print(f"      ✏️  Updates: {updates:,}")
            print(f"      🗑️  Deletes: {deletes:,}")
            print(f"      💀 Dead Tuples: {dead:,}")
            print(f"      🧹 Last Vacuum: {vac or 'Never'}")
            print(f"      🔧 Last Analyze: {analyze or 'Never'}")
            print()
        
        # 7. Security recommendations
        print("7️⃣ SECURITY RECOMMENDATIONS:")
        print("-" * 29)
        
        recommendations = []
        
        # Check if there are too many active connections
        if len(active_connections) > 10:
            recommendations.append("⚠️ High number of active connections detected")
        
        # Check for external connections
        external_connections = [conn for conn in active_connections if conn[3] and not conn[3].startswith('127.')]
        if external_connections:
            recommendations.append(f"🌐 {len(external_connections)} external connections detected")
        
        # Check for old connections
        old_connections = [conn for conn in active_connections if conn[10] > 3600]  # > 1 hour
        if old_connections:
            recommendations.append(f"⏰ {len(old_connections)} connections older than 1 hour")
        
        if recommendations:
            for rec in recommendations:
                print(f"   {rec}")
        else:
            print("   ✅ No immediate security concerns detected")
        
        print()
        print("8️⃣ AUDIT SUMMARY:")
        print("-" * 16)
        print(f"   🔍 Total Active Connections: {len(active_connections)}")
        print(f"   🌐 External Connections: {len(external_connections) if 'external_connections' in locals() else 0}")
        print(f"   ⚠️ Security Alerts: {len(recommendations)}")
        print(f"   📊 Database Health: {'Good' if len(recommendations) == 0 else 'Needs Attention'}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error during security audit: {str(e)}")
        return False

def main():
    """Main execution"""
    print("🔒 DATABASE SECURITY AUDIT")
    print("=" * 50)
    
    success = check_database_security()
    
    if success:
        print("\n✅ Security audit completed!")
        print("💡 Review the results above for any suspicious activity")
    else:
        print("\n❌ Security audit failed")
        print("💡 Check your database connection and permissions")

if __name__ == "__main__":
    main() 