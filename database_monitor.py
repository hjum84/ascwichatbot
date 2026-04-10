import os
from datetime import datetime
from sqlalchemy import text
from models import get_db, close_db, DB_TYPE, DATABASE_URL
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Database size limits (in bytes)
DB_MAX_SIZE_BYTES = int(os.getenv('DB_MAX_SIZE_BYTES', 1073741824))  # 1GB default
DB_SIZE_LIMIT = DB_MAX_SIZE_BYTES  # Use max size as limit
CHAT_HISTORY_LIMIT = 500 * 1024 * 1024  # 500MB
WARNING_THRESHOLD = 0.8  # 80% of limit

def format_bytes(bytes_value):
    """Format bytes to human readable format"""
    if bytes_value == 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"

def _build_fallback_result(source='error'):
    """Build a fallback result dict for when queries fail"""
    return {
        'total_size': "Error",
        'total_size_bytes': 0,
        'total_messages': 0,
        'total_chatbots': 0,
        'unique_users': 0,
        'timestamp': datetime.utcnow(),
        'max_size_bytes': DB_MAX_SIZE_BYTES,
        'max_size_pretty': "1.0 GB",
        'percent_used': 0,
        'remaining_bytes': DB_MAX_SIZE_BYTES,
        'remaining_pretty': "1.0 GB",
        'table_stats': {},
        'sorted_tables': [],
        'total_tables_count': 0,
        'db_breakdown': {},
        'total_tables_size_bytes': 0,
        'total_tables_size_pretty': '0 B',
        'capacity_source': f'{source}_fallback',
        'env_max_size': DB_MAX_SIZE_BYTES,
        'detection_successful': False,
    }

def _get_database_size_sqlite():
    """Get database statistics for SQLite (free local database)"""
    db = get_db()
    try:
        # Get file size of the SQLite database
        db_path = DATABASE_URL.replace("sqlite:///", "")
        if os.path.exists(db_path):
            total_db_bytes = os.path.getsize(db_path)
        else:
            total_db_bytes = 0

        total_db_size = format_bytes(total_db_bytes)
        actual_max_size = DB_MAX_SIZE_BYTES

        # Get row counts safely
        def safe_count(query):
            try:
                return db.execute(text(query)).scalar() or 0
            except Exception:
                return 0

        total_messages = safe_count("SELECT COUNT(*) FROM chat_history")
        total_chatbots = safe_count("SELECT COUNT(*) FROM chatbot_contents")
        unique_users = safe_count("SELECT COUNT(DISTINCT user_id) FROM chat_history")

        # Build table stats
        table_names = ['chat_history', 'chatbot_contents', 'users', 'authorized_users',
                       'user_lo_root_ids', 'chatbot_lo_root_association']
        table_stats = {}
        total_tables_size = 0

        for tname in table_names:
            row_count = safe_count(f"SELECT COUNT(*) FROM {tname}")
            estimated_size = max(4096, row_count * 200)
            total_tables_size += estimated_size
            table_stats[tname] = {
                'name': tname,
                'size_pretty': format_bytes(estimated_size),
                'size_bytes': estimated_size,
                'table_size_pretty': format_bytes(estimated_size),
                'table_size_bytes': estimated_size,
                'index_size_bytes': 0,
                'index_size_pretty': '0 B',
                'percentage': 0,
                'row_count': row_count,
            }

        for tname in table_stats:
            if total_db_bytes > 0:
                table_stats[tname]['percentage'] = round(
                    (table_stats[tname]['size_bytes'] / total_db_bytes) * 100, 2)
            table_stats[tname]['percentage_of_total_capacity'] = round(
                (table_stats[tname]['size_bytes'] / actual_max_size) * 100, 3
            ) if actual_max_size > 0 else 0

        used_bytes = total_db_bytes
        remaining_bytes = max(0, actual_max_size - used_bytes)
        percent_used = round((used_bytes / actual_max_size) * 100, 2) if actual_max_size > 0 else 0

        max_size_mb = actual_max_size // (1024 * 1024)
        max_size_gb = max_size_mb / 1024
        max_size_pretty = f"{max_size_gb:.1f} GB" if max_size_gb >= 1 else f"{max_size_mb} MB"

        sorted_tables = sorted(table_stats.values(), key=lambda x: x['size_bytes'], reverse=True)

        db_breakdown = {
            'User Tables': {
                'type': 'User Tables',
                'size_bytes': total_tables_size,
                'size_pretty': format_bytes(total_tables_size),
                'percentage': round((total_tables_size / total_db_bytes) * 100, 2) if total_db_bytes > 0 else 0,
                'percentage_of_total_capacity': round((total_tables_size / actual_max_size) * 100, 3) if actual_max_size > 0 else 0,
            }
        }

        return {
            'total_size': total_db_size,
            'total_size_bytes': total_db_bytes,
            'total_messages': total_messages,
            'total_chatbots': total_chatbots,
            'unique_users': unique_users,
            'timestamp': datetime.utcnow(),
            'max_size_bytes': actual_max_size,
            'max_size_pretty': max_size_pretty,
            'percent_used': percent_used,
            'remaining_bytes': remaining_bytes,
            'remaining_pretty': format_bytes(remaining_bytes),
            'table_stats': table_stats,
            'sorted_tables': sorted_tables,
            'total_tables_count': len(table_stats),
            'db_breakdown': db_breakdown,
            'total_tables_size_bytes': total_tables_size,
            'total_tables_size_pretty': format_bytes(total_tables_size),
            'capacity_source': 'sqlite_file',
            'env_max_size': DB_MAX_SIZE_BYTES,
            'detection_successful': True,
        }
    except Exception as e:
        logger.error(f"Error in SQLite get_database_size: {e}")
        return _build_fallback_result('sqlite_error')
    finally:
        try:
            close_db(db)
        except:
            pass


def get_database_size():
    """Get comprehensive database statistics with table-by-table breakdown"""
    if DB_TYPE == "sqlite":
        return _get_database_size_sqlite()

    # --- PostgreSQL path (kept for future use if you re-subscribe) ---
    db = get_db()
    try:
        try:
            capacity_result = db.execute(text("""
                WITH system_info AS (
                    SELECT 
                        CASE 
                            WHEN EXISTS (SELECT 1 FROM pg_tablespace WHERE spcname != 'pg_default') THEN
                                (SELECT pg_tablespace_size(oid) FROM pg_tablespace WHERE spcname != 'pg_default' LIMIT 1)
                            ELSE NULL
                        END as tablespace_size,
                        CASE 
                            WHEN has_function_privilege('pg_stat_file(text)', 'execute') THEN
                                (SELECT (pg_stat_file('.')).size * 1000 FROM pg_stat_file('.') WHERE (pg_stat_file('.')).isdir LIMIT 1)
                            ELSE NULL
                        END as disk_info,
                        CASE 
                            WHEN current_setting('shared_buffers', true) ~ '^[0-9]+kB$' THEN
                                (regexp_replace(current_setting('shared_buffers'), '[^0-9]', '', 'g')::bigint * 1024 * 8)
                            WHEN current_setting('shared_buffers', true) ~ '^[0-9]+MB$' THEN
                                (regexp_replace(current_setting('shared_buffers'), '[^0-9]', '', 'g')::bigint * 1024 * 1024 * 8)
                            ELSE NULL
                        END as estimated_from_buffers,
                        pg_database_size(current_database()) as current_db_size,
                        CASE 
                            WHEN current_setting('max_wal_size', true) ~ '^[0-9]+GB$' THEN
                                (regexp_replace(current_setting('max_wal_size'), '[^0-9]', '', 'g')::bigint * 1024 * 1024 * 1024 * 50)
                            WHEN current_setting('max_wal_size', true) ~ '^[0-9]+MB$' THEN
                                (regexp_replace(current_setting('max_wal_size'), '[^0-9]', '', 'g')::bigint * 1024 * 1024 * 50)
                            ELSE NULL
                        END as estimated_from_wal
                ),
                capacity_detection AS (
                    SELECT 
                        tablespace_size, disk_info, estimated_from_buffers, estimated_from_wal, current_db_size,
                        CASE 
                            WHEN tablespace_size IS NOT NULL AND tablespace_size > current_db_size THEN tablespace_size
                            WHEN estimated_from_buffers IS NOT NULL AND estimated_from_buffers > current_db_size AND estimated_from_buffers < :max_reasonable_size THEN estimated_from_buffers
                            WHEN estimated_from_wal IS NOT NULL AND estimated_from_wal > current_db_size AND estimated_from_wal < :max_reasonable_size THEN estimated_from_wal
                            ELSE :fallback_size
                        END as detected_capacity
                    FROM system_info
                )
                SELECT detected_capacity, current_db_size, tablespace_size, estimated_from_buffers, estimated_from_wal, 'system_detected' as detection_method
                FROM capacity_detection
            """), {
                'fallback_size': DB_MAX_SIZE_BYTES,
                'max_reasonable_size': 100 * 1024 * 1024 * 1024
            })
            capacity_info = capacity_result.fetchone()
            if capacity_info and capacity_info[0] > DB_MAX_SIZE_BYTES:
                actual_max_size = capacity_info[0]
                capacity_source = f"detected_{capacity_info[5]}"
            else:
                actual_max_size = DB_MAX_SIZE_BYTES
                capacity_source = 'environment_fallback'
        except Exception as e:
            logger.warning(f"Database capacity detection failed: {e}")
            actual_max_size = DB_MAX_SIZE_BYTES
            capacity_source = 'error_fallback'
            try:
                db.rollback()
            except:
                pass

        try:
            overall_result = db.execute(text("""
                SELECT 
                    pg_size_pretty(pg_database_size(current_database())) as total_db_size,
                    pg_database_size(current_database()) as total_db_bytes,
                    (SELECT COUNT(*) FROM chat_history) as total_messages,
                    (SELECT COUNT(*) FROM chatbot_contents) as total_chatbots,
                    (SELECT COUNT(DISTINCT user_id) FROM chat_history) as unique_users
            """))
            overall_stats = overall_result.fetchone()
            db.commit()
        except Exception as e:
            logger.error(f"Failed to get overall database stats: {e}")
            db.rollback()
            overall_stats = ("0 MB", 0, 0, 0, 0)

        try:
            tables_result = db.execute(text("""
                WITH table_stats AS (
                    SELECT schemaname, tablename,
                        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size_pretty,
                        pg_total_relation_size(schemaname||'.'||tablename) as size_bytes,
                        pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size_pretty,
                        pg_relation_size(schemaname||'.'||tablename) as table_size_bytes,
                        (pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as index_size_bytes
                    FROM pg_tables WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
                ) SELECT * FROM table_stats ORDER BY size_bytes DESC
            """))
            db.commit()
        except Exception as e:
            logger.error(f"Failed to get table statistics: {e}")
            db.rollback()
            tables_result = []

        try:
            db_breakdown_result = db.execute(text("""
                WITH total_db_size AS (
                    SELECT pg_database_size(current_database()) as total_bytes
                ),
                user_tables AS (
                    SELECT 'User Tables' as component_type,
                        COALESCE(SUM(pg_total_relation_size(schemaname||'.'||tablename)), 0) as size_bytes
                    FROM pg_tables WHERE schemaname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ),
                user_indexes AS (
                    SELECT 'User Indexes' as component_type,
                        COALESCE(SUM(pg_indexes_size(schemaname||'.'||tablename)), 0) as size_bytes
                    FROM pg_tables WHERE schemaname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ),
                system_overhead AS (
                    SELECT 'System Overhead' as component_type,
                        GREATEST(tds.total_bytes * 0.20, 1048576)::bigint as size_bytes
                    FROM total_db_size tds
                ),
                all_components AS (
                    SELECT * FROM user_tables UNION ALL SELECT * FROM user_indexes UNION ALL SELECT * FROM system_overhead
                ),
                accounted_total AS (
                    SELECT SUM(size_bytes) as accounted_bytes FROM all_components
                ),
                final_breakdown AS (
                    SELECT ac.component_type, ac.size_bytes,
                        pg_size_pretty(ac.size_bytes) as size_pretty,
                        ROUND((ac.size_bytes::numeric / tds.total_bytes::numeric) * 100, 2) as percentage
                    FROM all_components ac, total_db_size tds WHERE ac.size_bytes > 0
                    UNION ALL
                    SELECT 'Unaccounted/Other' as component_type,
                        GREATEST(0, tds.total_bytes - at.accounted_bytes) as size_bytes,
                        pg_size_pretty(GREATEST(0, tds.total_bytes - at.accounted_bytes)) as size_pretty,
                        ROUND((GREATEST(0, tds.total_bytes - at.accounted_bytes)::numeric / tds.total_bytes::numeric) * 100, 2) as percentage
                    FROM accounted_total at, total_db_size tds
                    WHERE (tds.total_bytes - at.accounted_bytes) > 1024
                )
                SELECT component_type, size_bytes, size_pretty, percentage FROM final_breakdown WHERE size_bytes > 0 ORDER BY size_bytes DESC
            """))
            db.commit()
        except Exception as e:
            logger.error(f"Failed to get database breakdown: {e}")
            db.rollback()
            db_breakdown_result = []

        try:
            row_counts_result = db.execute(text("""
                SELECT 'chat_history' as table_name, COUNT(*) as row_count FROM chat_history
                UNION ALL SELECT 'chatbot_contents', COUNT(*) FROM chatbot_contents
                UNION ALL SELECT 'users', COUNT(*) FROM users
                UNION ALL SELECT 'authorized_users', COUNT(*) FROM authorized_users
                UNION ALL SELECT 'user_lo_root_ids', COUNT(*) FROM user_lo_root_ids
                UNION ALL SELECT 'chatbot_lo_root_association', COUNT(*) FROM chatbot_lo_root_association
            """))
            db.commit()
        except Exception as e:
            logger.error(f"Failed to get row counts: {e}")
            db.rollback()
            row_counts_result = []

        table_stats = {}
        total_tables_size = 0
        if tables_result:
            try:
                for row in tables_result:
                    schema, table_name, size_pretty, size_bytes, table_size_pretty, table_size_bytes, index_size_bytes = row
                    total_tables_size += size_bytes
                    table_stats[table_name] = {
                        'name': table_name, 'size_pretty': size_pretty, 'size_bytes': size_bytes,
                        'table_size_pretty': table_size_pretty, 'table_size_bytes': table_size_bytes,
                        'index_size_bytes': index_size_bytes, 'index_size_pretty': format_bytes(index_size_bytes),
                        'percentage': 0, 'row_count': 0
                    }
            except Exception as e:
                logger.error(f"Error processing table statistics: {e}")
                table_stats = {}

        db_breakdown = {}
        if db_breakdown_result:
            try:
                for row in db_breakdown_result:
                    component_type, size_bytes, size_pretty, percentage = row
                    db_breakdown[component_type] = {
                        'type': component_type, 'size_bytes': size_bytes, 'size_pretty': size_pretty,
                        'percentage': percentage,
                        'percentage_of_total_capacity': round((size_bytes / actual_max_size) * 100, 3) if actual_max_size > 0 else 0
                    }
            except Exception as e:
                logger.error(f"Error processing database breakdown: {e}")
                db_breakdown = {}

        if row_counts_result:
            try:
                for row in row_counts_result:
                    table_name, row_count = row
                    if table_name in table_stats:
                        table_stats[table_name]['row_count'] = row_count
            except Exception as e:
                logger.error(f"Error processing row counts: {e}")

        current_used_bytes = overall_stats[1] if overall_stats else 0
        for table_name in table_stats:
            table_stats[table_name]['percentage'] = round(
                (table_stats[table_name]['size_bytes'] / current_used_bytes) * 100, 2
            ) if current_used_bytes > 0 else 0
            table_stats[table_name]['percentage_of_total_capacity'] = round(
                (table_stats[table_name]['size_bytes'] / actual_max_size) * 100, 3
            ) if actual_max_size > 0 else 0

        try:
            used_bytes = overall_stats[1] if overall_stats else 0
            remaining_bytes = max(0, actual_max_size - used_bytes)
            max_size_mb = actual_max_size // (1024 * 1024)
            max_size_gb = max_size_mb / 1024
            max_size_pretty = f"{max_size_gb:.1f} GB" if max_size_gb >= 1 else f"{max_size_mb} MB"
            percent_used = round((used_bytes / actual_max_size) * 100, 2) if actual_max_size > 0 else 0
            sorted_tables = sorted(table_stats.values(), key=lambda x: x['size_bytes'], reverse=True) if table_stats else []

            return {
                'total_size': overall_stats[0] if overall_stats else "0 MB",
                'total_size_bytes': overall_stats[1] if overall_stats else 0,
                'total_messages': overall_stats[2] if overall_stats else 0,
                'total_chatbots': overall_stats[3] if overall_stats else 0,
                'unique_users': overall_stats[4] if overall_stats else 0,
                'timestamp': datetime.utcnow(),
                'max_size_bytes': actual_max_size,
                'max_size_pretty': max_size_pretty,
                'percent_used': percent_used,
                'remaining_bytes': remaining_bytes,
                'remaining_pretty': format_bytes(remaining_bytes),
                'table_stats': table_stats,
                'sorted_tables': sorted_tables,
                'total_tables_count': len(table_stats),
                'db_breakdown': db_breakdown,
                'total_tables_size_bytes': total_tables_size,
                'total_tables_size_pretty': format_bytes(total_tables_size),
                'capacity_source': capacity_source,
                'env_max_size': DB_MAX_SIZE_BYTES,
                'detection_successful': actual_max_size != DB_MAX_SIZE_BYTES,
            }
        except Exception as e:
            logger.error(f"Error in final processing: {e}")
            return _build_fallback_result('error')
    except Exception as e:
        logger.error(f"Fatal error in get_database_size: {e}")
        return _build_fallback_result('fatal_error')
    finally:
        try:
            close_db(db)
        except:
            pass

def get_storage_health_status(percent_used):
    """Get storage health status based on usage percentage"""
    if percent_used >= 90:
        return {
            'status': 'critical',
            'color': 'danger',
            'icon': 'exclamation-triangle-fill',
            'message': 'Storage critically low - immediate action required'
        }
    elif percent_used >= 80:
        return {
            'status': 'warning',
            'color': 'warning', 
            'icon': 'exclamation-triangle',
            'message': 'Storage running low - consider cleanup or upgrade'
        }
    elif percent_used >= 60:
        return {
            'status': 'caution',
            'color': 'info',
            'icon': 'info-circle',
            'message': 'Storage usage is moderate - monitor regularly'
        }
    else:
        return {
            'status': 'healthy',
            'color': 'success',
            'icon': 'check-circle',
            'message': 'Storage usage is healthy'
        }

def check_database_limits():
    """Check if database size is approaching limits"""
    stats = get_database_size()
    alerts = []
    
    if stats['total_size_bytes'] > DB_SIZE_LIMIT * WARNING_THRESHOLD:
        alerts.append({
            'level': 'warning',
            'message': f'Database size ({stats["total_size"]}) is approaching the limit of {DB_SIZE_LIMIT / (1024*1024*1024):.2f} GB'
        })
    
    if stats['total_messages'] > CHAT_HISTORY_LIMIT * WARNING_THRESHOLD:
        alerts.append({
            'level': 'warning',
            'message': f'Chat history size ({stats["total_messages"]}) is approaching the limit of {CHAT_HISTORY_LIMIT / (1024*1024):.2f} MB'
        })
    
    return alerts

def send_database_alert_email(alerts):
    """Send email alerts to admin"""
    if not alerts:
        return
        
    admin_email = os.getenv('ADMIN_EMAIL')
    if not admin_email:
        logger.warning("ADMIN_EMAIL not set in environment variables")
        return
        
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_username = os.getenv('SMTP_USERNAME')
    smtp_password = os.getenv('SMTP_PASSWORD')
    
    if not all([smtp_server, smtp_username, smtp_password]):
        logger.warning("SMTP configuration not complete")
        return
    
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = admin_email
        msg['Subject'] = "Database Size Alert"
        
        body = "The following database size alerts have been triggered:\n\n"
        for alert in alerts:
            body += f"- {alert['message']}\n"
        
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
            
        logger.info(f"Alert email sent to {admin_email}")
    except Exception as e:
        logger.error(f"Failed to send alert email: {str(e)}")

def setup_database_monitoring():
    """Setup scheduled database monitoring"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_database_limits, 'cron', hour=0)
    scheduler.add_job(check_database_limits, 'interval', hours=1)
    scheduler.start()
    logger.info("Database monitoring scheduler started")
