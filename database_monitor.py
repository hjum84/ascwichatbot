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
DEFAULT_DB_MAX_SIZE_BYTES = 536870912  # 0.5 GB fallback only
DB_MAX_SIZE_ENV = os.getenv('DB_MAX_SIZE_BYTES')
DB_MAX_SIZE_BYTES = int(DB_MAX_SIZE_ENV) if DB_MAX_SIZE_ENV else DEFAULT_DB_MAX_SIZE_BYTES
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
        'max_size_pretty': format_bytes(DB_MAX_SIZE_BYTES),
        'percent_used': 0,
        'remaining_bytes': DB_MAX_SIZE_BYTES,
        'remaining_pretty': format_bytes(DB_MAX_SIZE_BYTES),
        'table_stats': {},
        'sorted_tables': [],
        'total_tables_count': 0,
        'db_breakdown': {},
        'total_tables_size_bytes': 0,
        'total_tables_size_pretty': '0 B',
        'capacity_source': f'{source}_fallback',
        'capacity_source_label': 'Fallback',
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

        page_size = safe_count("PRAGMA page_size")
        page_count = safe_count("PRAGMA page_count")
        freelist_count = safe_count("PRAGMA freelist_count")
        estimated_reclaimable_bytes = freelist_count * page_size if page_size and freelist_count else 0

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

        live_table_bytes = max(0, total_tables_size - estimated_reclaimable_bytes)
        accounted_bytes = live_table_bytes + estimated_reclaimable_bytes
        other_internal_bytes = max(0, total_db_bytes - accounted_bytes)

        db_breakdown = {
            'Live Table Data': {
                'type': 'Live Table Data',
                'size_bytes': live_table_bytes,
                'size_pretty': format_bytes(live_table_bytes),
                'percentage': round((live_table_bytes / total_db_bytes) * 100, 2) if total_db_bytes > 0 else 0,
                'percentage_of_total_capacity': round((live_table_bytes / actual_max_size) * 100, 3) if actual_max_size > 0 else 0,
            },
            'Estimated Reclaimable': {
                'type': 'Estimated Reclaimable',
                'size_bytes': estimated_reclaimable_bytes,
                'size_pretty': format_bytes(estimated_reclaimable_bytes),
                'percentage': round((estimated_reclaimable_bytes / total_db_bytes) * 100, 2) if total_db_bytes > 0 else 0,
                'percentage_of_total_capacity': round((estimated_reclaimable_bytes / actual_max_size) * 100, 3) if actual_max_size > 0 else 0,
            }
        }
        if other_internal_bytes > 0:
            db_breakdown['Other Internal'] = {
                'type': 'Other Internal',
                'size_bytes': other_internal_bytes,
                'size_pretty': format_bytes(other_internal_bytes),
                'percentage': round((other_internal_bytes / total_db_bytes) * 100, 2) if total_db_bytes > 0 else 0,
                'percentage_of_total_capacity': round((other_internal_bytes / actual_max_size) * 100, 3) if actual_max_size > 0 else 0,
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
            'capacity_source': 'sqlite_file_plus_configured_limit',
            'capacity_source_label': 'Configured Limit',
            'env_max_size': DB_MAX_SIZE_BYTES,
            'detection_successful': bool(DB_MAX_SIZE_ENV),
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

    # --- PostgreSQL path ---
    db = get_db()
    try:
        actual_max_size = DB_MAX_SIZE_BYTES
        capacity_source = 'configured_env_limit' if DB_MAX_SIZE_ENV else 'default_fallback_limit'
        capacity_source_label = 'Configured Limit' if DB_MAX_SIZE_ENV else 'Fallback Default'

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
                WITH base AS (
                    SELECT
                        t.schemaname,
                        t.tablename,
                        pg_total_relation_size(format('%I.%I', t.schemaname, t.tablename)) AS total_size_bytes,
                        pg_relation_size(format('%I.%I', t.schemaname, t.tablename)) AS table_size_bytes,
                        pg_indexes_size(format('%I.%I', t.schemaname, t.tablename)) AS index_size_bytes,
                        GREATEST(
                            pg_total_relation_size(format('%I.%I', t.schemaname, t.tablename))
                            - pg_relation_size(format('%I.%I', t.schemaname, t.tablename))
                            - pg_indexes_size(format('%I.%I', t.schemaname, t.tablename)),
                            0
                        ) AS toast_size_bytes
                    FROM pg_tables t
                    WHERE t.schemaname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ),
                stats AS (
                    SELECT
                        schemaname,
                        relname AS tablename,
                        COALESCE(n_live_tup, 0) AS n_live_tup,
                        COALESCE(n_dead_tup, 0) AS n_dead_tup
                    FROM pg_stat_user_tables
                )
                SELECT
                    b.schemaname,
                    b.tablename,
                    b.total_size_bytes,
                    b.table_size_bytes,
                    b.index_size_bytes,
                    b.toast_size_bytes,
                    COALESCE(s.n_live_tup, 0) AS n_live_tup,
                    COALESCE(s.n_dead_tup, 0) AS n_dead_tup
                FROM base b
                LEFT JOIN stats s
                    ON s.schemaname = b.schemaname AND s.tablename = b.tablename
                ORDER BY b.total_size_bytes DESC
            """))
            db.commit()
        except Exception as e:
            logger.error(f"Failed to get table statistics: {e}")
            db.rollback()
            tables_result = []

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
        live_table_total = 0
        dead_tuple_estimate_total = 0
        index_total = 0
        toast_total = 0
        if tables_result:
            try:
                for row in tables_result:
                    (
                        schema,
                        table_name,
                        size_bytes,
                        table_size_bytes,
                        index_size_bytes,
                        toast_size_bytes,
                        n_live_tup,
                        n_dead_tup
                    ) = row

                    total_tuples = max((n_live_tup or 0) + (n_dead_tup or 0), 0)
                    avg_tuple_bytes = (table_size_bytes / total_tuples) if total_tuples > 0 else 0
                    dead_estimate_bytes = int(min(table_size_bytes, (n_dead_tup or 0) * avg_tuple_bytes))
                    live_table_bytes = max(0, table_size_bytes - dead_estimate_bytes)

                    total_tables_size += size_bytes
                    live_table_total += live_table_bytes
                    dead_tuple_estimate_total += dead_estimate_bytes
                    index_total += max(index_size_bytes, 0)
                    toast_total += max(toast_size_bytes, 0)
                    table_stats[table_name] = {
                        'name': table_name,
                        'size_pretty': format_bytes(size_bytes),
                        'size_bytes': size_bytes,
                        'table_size_pretty': format_bytes(table_size_bytes),
                        'table_size_bytes': table_size_bytes,
                        'live_table_size_bytes': live_table_bytes,
                        'live_table_size_pretty': format_bytes(live_table_bytes),
                        'dead_estimate_bytes': dead_estimate_bytes,
                        'dead_estimate_pretty': format_bytes(dead_estimate_bytes),
                        'index_size_bytes': index_size_bytes,
                        'index_size_pretty': format_bytes(index_size_bytes),
                        'toast_size_bytes': toast_size_bytes,
                        'toast_size_pretty': format_bytes(toast_size_bytes),
                        'n_dead_tup': int(n_dead_tup or 0),
                        'percentage': 0,
                        'row_count': 0
                    }
            except Exception as e:
                logger.error(f"Error processing table statistics: {e}")
                table_stats = {}

        db_breakdown = {}
        current_used_bytes = overall_stats[1] if overall_stats else 0
        other_internal_bytes = max(
            0,
            current_used_bytes - (live_table_total + dead_tuple_estimate_total + index_total + toast_total)
        )

        breakdown_components = [
            ("Live Table Data", live_table_total),
            ("Estimated Dead/Reclaimable", dead_tuple_estimate_total),
            ("Indexes", index_total),
            ("TOAST / Large Values", toast_total),
        ]
        if other_internal_bytes > 0:
            breakdown_components.append(("Other Internal", other_internal_bytes))

        for component_type, size_bytes in breakdown_components:
            if size_bytes <= 0:
                continue
            db_breakdown[component_type] = {
                'type': component_type,
                'size_bytes': size_bytes,
                'size_pretty': format_bytes(size_bytes),
                'percentage': round((size_bytes / current_used_bytes) * 100, 2) if current_used_bytes > 0 else 0,
                'percentage_of_total_capacity': round((size_bytes / actual_max_size) * 100, 3) if actual_max_size > 0 else 0
            }

        if row_counts_result:
            try:
                for row in row_counts_result:
                    table_name, row_count = row
                    if table_name in table_stats:
                        table_stats[table_name]['row_count'] = row_count
            except Exception as e:
                logger.error(f"Error processing row counts: {e}")

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
                'capacity_source_label': capacity_source_label,
                'env_max_size': DB_MAX_SIZE_BYTES,
                'detection_successful': bool(DB_MAX_SIZE_ENV),
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
    
    chat_history_size = (
        stats.get('table_stats', {})
        .get('chat_history', {})
        .get('size_bytes', 0)
    )
    if chat_history_size > CHAT_HISTORY_LIMIT * WARNING_THRESHOLD:
        alerts.append({
            'level': 'warning',
            'message': (
                f'Chat history storage ({format_bytes(chat_history_size)}) is approaching '
                f'the limit of {CHAT_HISTORY_LIMIT / (1024*1024):.2f} MB'
            )
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
