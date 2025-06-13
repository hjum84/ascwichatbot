import os
from datetime import datetime
from sqlalchemy import text
from models import get_db, close_db
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

def get_database_size():
    """Get comprehensive database statistics with table-by-table breakdown"""
    db = get_db()
    try:
        # Get REAL database capacity from PostgreSQL system (Render plan limits)
        try:
            # Query multiple PostgreSQL system sources to detect actual storage limits
            capacity_result = db.execute(text("""
                WITH system_info AS (
                    SELECT 
                        -- Method 1: Check tablespace size (Render may set tablespace quotas)
                        CASE 
                            WHEN EXISTS (SELECT 1 FROM pg_tablespace WHERE spcname != 'pg_default') THEN
                                (SELECT pg_tablespace_size(oid) FROM pg_tablespace WHERE spcname != 'pg_default' LIMIT 1)
                            ELSE NULL
                        END as tablespace_size,
                        
                        -- Method 2: Try to get disk space info from pg_stat_file (if accessible)
                        CASE 
                            WHEN has_function_privilege('pg_stat_file(text)', 'execute') THEN
                                -- This might work in some managed environments
                                (SELECT (pg_stat_file('.')).size * 1000 FROM pg_stat_file('.') WHERE (pg_stat_file('.')).isdir LIMIT 1)
                            ELSE NULL
                        END as disk_info,
                        
                        -- Method 3: Check for Render-specific settings or constraints
                        CASE 
                            WHEN current_setting('shared_buffers', true) ~ '^[0-9]+kB$' THEN
                                -- Extract shared_buffers and estimate from that
                                (regexp_replace(current_setting('shared_buffers'), '[^0-9]', '', 'g')::bigint * 1024 * 8)
                            WHEN current_setting('shared_buffers', true) ~ '^[0-9]+MB$' THEN
                                (regexp_replace(current_setting('shared_buffers'), '[^0-9]', '', 'g')::bigint * 1024 * 1024 * 8)
                            ELSE NULL
                        END as estimated_from_buffers,
                        
                        -- Method 4: Database cluster size approach
                        pg_database_size(current_database()) as current_db_size,
                        
                        -- Method 5: Check WAL and temp file settings for capacity hints
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
                        tablespace_size,
                        disk_info,
                        estimated_from_buffers,
                        estimated_from_wal,
                        current_db_size,
                        -- Smart logic to pick the most reliable capacity estimate
                        CASE 
                            WHEN tablespace_size IS NOT NULL AND tablespace_size > current_db_size THEN tablespace_size
                            WHEN estimated_from_buffers IS NOT NULL AND estimated_from_buffers > current_db_size AND estimated_from_buffers < :max_reasonable_size THEN estimated_from_buffers
                            WHEN estimated_from_wal IS NOT NULL AND estimated_from_wal > current_db_size AND estimated_from_wal < :max_reasonable_size THEN estimated_from_wal
                            ELSE :fallback_size
                        END as detected_capacity
                    FROM system_info
                )
                SELECT 
                    detected_capacity,
                    current_db_size,
                    tablespace_size,
                    estimated_from_buffers,
                    estimated_from_wal,
                    'system_detected' as detection_method
                FROM capacity_detection
            """), {
                'fallback_size': DB_MAX_SIZE_BYTES,
                'max_reasonable_size': 100 * 1024 * 1024 * 1024  # 100GB max reasonable
            })
            
            capacity_info = capacity_result.fetchone()
            
            if capacity_info and capacity_info[0] > DB_MAX_SIZE_BYTES:
                actual_max_size = capacity_info[0]
                capacity_source = f"detected_{capacity_info[5]}"
                logger.info(f"Detected database capacity: {actual_max_size / (1024*1024*1024):.2f} GB using {capacity_info[5]}")
            else:
                actual_max_size = DB_MAX_SIZE_BYTES
                capacity_source = 'environment_fallback'
                logger.info(f"Using environment capacity: {actual_max_size / (1024*1024*1024):.2f} GB")
                
        except Exception as e:
            # If detection fails, use environment setting
            logger.warning(f"Database capacity detection failed: {e}")
            actual_max_size = DB_MAX_SIZE_BYTES
            capacity_source = 'error_fallback'
            # Rollback any failed transaction before continuing
            try:
                db.rollback()
            except:
                pass
        
        # Get overall database size with proper transaction handling
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
            # Use fallback values
            overall_stats = ("0 MB", 0, 0, 0, 0)
        
        # Get detailed table-by-table statistics with proper transaction handling
        try:
            tables_result = db.execute(text("""
                WITH table_stats AS (
                    SELECT 
                        schemaname,
                        tablename,
                        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size_pretty,
                        pg_total_relation_size(schemaname||'.'||tablename) as size_bytes,
                        pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size_pretty,
                        pg_relation_size(schemaname||'.'||tablename) as table_size_bytes,
                        (pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as index_size_bytes
                    FROM pg_tables 
                    WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
                )
                SELECT * FROM table_stats
                ORDER BY size_bytes DESC
            """))
            db.commit()
        except Exception as e:
            logger.error(f"Failed to get table statistics: {e}")
            db.rollback()
            tables_result = []
        
        # Get complete database breakdown including system overhead
        try:
            db_breakdown_result = db.execute(text("""
                WITH total_db_size AS (
                    SELECT pg_database_size(current_database()) as total_bytes
                ),
                user_tables AS (
                    -- Get all user tables total size (table + indexes)
                    SELECT 
                        'User Tables' as component_type,
                        COALESCE(SUM(pg_total_relation_size(schemaname||'.'||tablename)), 0) as size_bytes
                    FROM pg_tables 
                    WHERE schemaname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ),
                user_indexes AS (
                    -- Get user table indexes separately for better visibility
                    SELECT 
                        'User Indexes' as component_type,
                        COALESCE(SUM(pg_indexes_size(schemaname||'.'||tablename)), 0) as size_bytes
                    FROM pg_tables 
                    WHERE schemaname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ),
                system_overhead AS (
                    -- Calculate system overhead as a reasonable percentage of total DB size
                    -- This includes WAL files, temp files, system catalogs, etc.
                    SELECT 
                        'System Overhead' as component_type,
                        GREATEST(
                            tds.total_bytes * 0.20,  -- Assume 20% system overhead minimum
                            1048576  -- At least 1MB
                        )::bigint as size_bytes
                    FROM total_db_size tds
                ),
                all_components AS (
                    SELECT * FROM user_tables
                    UNION ALL SELECT * FROM user_indexes
                    UNION ALL SELECT * FROM system_overhead
                ),
                accounted_total AS (
                    SELECT SUM(size_bytes) as accounted_bytes FROM all_components
                ),
                final_breakdown AS (
                    -- Return all components with proper percentages
                    SELECT 
                        ac.component_type,
                        ac.size_bytes,
                        pg_size_pretty(ac.size_bytes) as size_pretty,
                        ROUND((ac.size_bytes::numeric / tds.total_bytes::numeric) * 100, 2) as percentage
                    FROM all_components ac, total_db_size tds
                    WHERE ac.size_bytes > 0
                    
                    UNION ALL
                    
                    -- Add remaining unaccounted space (should be minimal now)
                    SELECT 
                        'Unaccounted/Other' as component_type,
                        GREATEST(0, tds.total_bytes - at.accounted_bytes) as size_bytes,
                        pg_size_pretty(GREATEST(0, tds.total_bytes - at.accounted_bytes)) as size_pretty,
                        ROUND((GREATEST(0, tds.total_bytes - at.accounted_bytes)::numeric / tds.total_bytes::numeric) * 100, 2) as percentage
                    FROM accounted_total at, total_db_size tds
                    WHERE (tds.total_bytes - at.accounted_bytes) > 1024  -- Only show if > 1KB
                )
                SELECT 
                    component_type,
                    size_bytes,
                    size_pretty,
                    percentage
                FROM final_breakdown
                WHERE size_bytes > 0
                ORDER BY size_bytes DESC
            """))
            db.commit()
        except Exception as e:
            logger.error(f"Failed to get database breakdown: {e}")
            db.rollback()
            db_breakdown_result = []
        
        # Get row counts for each main table with proper transaction handling
        try:
            row_counts_result = db.execute(text("""
                SELECT 
                    'chat_history' as table_name, COUNT(*) as row_count FROM chat_history
                UNION ALL
                SELECT 
                    'chatbot_contents' as table_name, COUNT(*) as row_count FROM chatbot_contents
                UNION ALL
                SELECT 
                    'users' as table_name, COUNT(*) as row_count FROM users
                UNION ALL
                SELECT 
                    'authorized_users' as table_name, COUNT(*) as row_count FROM authorized_users
                UNION ALL
                SELECT 
                    'user_lo_root_ids' as table_name, COUNT(*) as row_count FROM user_lo_root_ids
                UNION ALL
                SELECT 
                    'chatbot_lo_root_association' as table_name, COUNT(*) as row_count FROM chatbot_lo_root_association
            """))
            db.commit()
        except Exception as e:
            logger.error(f"Failed to get row counts: {e}")
            db.rollback()
            row_counts_result = []
        
        # Process table statistics
        table_stats = {}
        total_tables_size = 0
        
        # Safely process tables_result
        if tables_result:
            try:
                for row in tables_result:
                    schema, table_name, size_pretty, size_bytes, table_size_pretty, table_size_bytes, index_size_bytes = row
                    total_tables_size += size_bytes
                    table_stats[table_name] = {
                        'name': table_name,
                        'size_pretty': size_pretty,
                        'size_bytes': size_bytes,
                        'table_size_pretty': table_size_pretty,
                        'table_size_bytes': table_size_bytes,
                        'index_size_bytes': index_size_bytes,
                        'index_size_pretty': format_bytes(index_size_bytes),
                        'percentage': 0,  # Will be calculated below
                        'row_count': 0    # Will be filled from row_counts
                    }
            except Exception as e:
                logger.error(f"Error processing table statistics: {e}")
                table_stats = {}
        
        # Process database breakdown components
        db_breakdown = {}
        if db_breakdown_result:
            try:
                for row in db_breakdown_result:
                    component_type, size_bytes, size_pretty, percentage = row
                    # For breakdown visualization: show percentage within USED space (16MB), not total capacity (1GB)
                    # This shows "how the current 16MB is composed" rather than "how much of 1GB each component uses"
                    db_breakdown[component_type] = {
                        'type': component_type,
                        'size_bytes': size_bytes,
                        'size_pretty': size_pretty,
                        'percentage': percentage,  # Keep original percentage (within used space)
                        'percentage_of_total_capacity': round((size_bytes / actual_max_size) * 100, 3) if actual_max_size > 0 else 0  # Add this for storage bar
                    }
            except Exception as e:
                logger.error(f"Error processing database breakdown: {e}")
                db_breakdown = {}
        
        # Add row counts safely
        if row_counts_result:
            try:
                for row in row_counts_result:
                    table_name, row_count = row
                    if table_name in table_stats:
                        table_stats[table_name]['row_count'] = row_count
            except Exception as e:
                logger.error(f"Error processing row counts: {e}")
        
        # Calculate percentages for table breakdown - use CURRENT USED SIZE for relative comparison
        # This shows "what portion of the currently used 16MB each table represents"
        current_used_bytes = overall_stats[1] if overall_stats else 0
        for table_name in table_stats:
            # For table breakdown: percentage within currently used space (16MB)
            table_stats[table_name]['percentage'] = round(
                (table_stats[table_name]['size_bytes'] / current_used_bytes) * 100, 2
            ) if current_used_bytes > 0 else 0
            # Also add percentage of total capacity for reference
            table_stats[table_name]['percentage_of_total_capacity'] = round(
                (table_stats[table_name]['size_bytes'] / actual_max_size) * 100, 3
            ) if actual_max_size > 0 else 0
        
        # Calculate remaining space using ACTUAL capacity
        try:
            used_bytes = overall_stats[1] if overall_stats else 0
            remaining_bytes = max(0, actual_max_size - used_bytes)
            
            # Format ACTUAL max size for display
            max_size_mb = actual_max_size // (1024 * 1024)
            max_size_gb = max_size_mb / 1024
            
            if max_size_gb >= 1:
                max_size_pretty = f"{max_size_gb:.1f} GB"
            else:
                max_size_pretty = f"{max_size_mb} MB"
                
            percent_used = round((used_bytes / actual_max_size) * 100, 2) if actual_max_size > 0 else 0
            
            # Sort tables by size for display
            sorted_tables = sorted(table_stats.values(), key=lambda x: x['size_bytes'], reverse=True) if table_stats else []
            
            return {
                # Overall statistics
                'total_size': overall_stats[0] if overall_stats else "0 MB",
                'total_size_bytes': overall_stats[1] if overall_stats else 0,
                'total_messages': overall_stats[2] if overall_stats else 0,
                'total_chatbots': overall_stats[3] if overall_stats else 0,
                'unique_users': overall_stats[4] if overall_stats else 0,
                'timestamp': datetime.utcnow(),
                
                # Capacity information - NOW USING ACTUAL DATABASE CAPACITY
                'max_size_bytes': actual_max_size,
                'max_size_pretty': max_size_pretty,
                'percent_used': percent_used,
                'remaining_bytes': remaining_bytes,
                'remaining_pretty': format_bytes(remaining_bytes),
                
                # Detailed breakdown
                'table_stats': table_stats,
                'sorted_tables': sorted_tables,
                'total_tables_count': len(table_stats),
                
                # Complete database breakdown (NEW)
                'db_breakdown': db_breakdown,
                'total_tables_size_bytes': total_tables_size,
                'total_tables_size_pretty': format_bytes(total_tables_size),
                
                # Debug info - detailed capacity detection
                'capacity_source': capacity_source,
                'env_max_size': DB_MAX_SIZE_BYTES,
                'detection_successful': actual_max_size != DB_MAX_SIZE_BYTES,
            }
        except Exception as e:
            logger.error(f"Error in final processing: {e}")
            # Return minimal fallback data
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
                'capacity_source': 'error_fallback',
                'env_max_size': DB_MAX_SIZE_BYTES,
                'detection_successful': False,
            }
    except Exception as e:
        logger.error(f"Fatal error in get_database_size: {e}")
        # Return absolute fallback
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
            'capacity_source': 'fatal_error',
            'env_max_size': DB_MAX_SIZE_BYTES,
            'detection_successful': False,
        }
    finally:
        try:
            close_db(db)
        except:
            pass

def format_bytes(bytes_value):
    """Format bytes to human readable format"""
    if bytes_value == 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"

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
    
    # Check total database size
    if stats['total_size_bytes'] > DB_SIZE_LIMIT * WARNING_THRESHOLD:
        alerts.append({
            'level': 'warning',
            'message': f'Database size ({stats["total_size"]}) is approaching the limit of {DB_SIZE_LIMIT / (1024*1024*1024):.2f} GB'
        })
    
    # Check chat history size
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
    
    # Check database size daily at midnight
    scheduler.add_job(check_database_limits, 'cron', hour=0)
    
    # Check database size hourly
    scheduler.add_job(check_database_limits, 'interval', hours=1)
    
    scheduler.start()
    logger.info("Database monitoring scheduler started") 