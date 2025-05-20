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
    """Get current database statistics"""
    db = get_db()
    try:
        result = db.execute(text("""
            SELECT 
                pg_size_pretty(pg_database_size(current_database())) as db_size,
                pg_size_pretty(pg_total_relation_size('chat_history')) as chat_history_size,
                pg_size_pretty(pg_total_relation_size('chatbot_contents')) as chatbot_contents_size,
                pg_database_size(current_database()) as db_size_bytes,
                pg_total_relation_size('chat_history') as chat_history_size_bytes,
                (SELECT COUNT(*) FROM chat_history) as total_messages,
                (SELECT COUNT(*) FROM chatbot_contents) as total_chatbots,
                (SELECT COUNT(DISTINCT user_id) FROM chat_history) as unique_users
        """))
        stats = result.fetchone()
        
        # Format max size for display
        max_size_mb = DB_MAX_SIZE_BYTES // (1024 * 1024)
        max_size_gb = max_size_mb / 1024
        
        if max_size_gb >= 1:
            max_size_pretty = f"{max_size_gb:.1f} GB"
        else:
            max_size_pretty = f"{max_size_mb} MB"
            
        percent_used = round((stats[3] / DB_MAX_SIZE_BYTES) * 100, 2)
        
        return {
            'total_size': stats[0],
            'chat_history_size': stats[1],
            'chatbot_contents_size': stats[2],
            'total_size_bytes': stats[3],
            'chat_history_size_bytes': stats[4],
            'total_messages': stats[5],
            'total_chatbots': stats[6],
            'unique_users': stats[7],
            'timestamp': datetime.utcnow(),
            'max_size_bytes': DB_MAX_SIZE_BYTES,
            'max_size_pretty': max_size_pretty,
            'percent_used': percent_used
        }
    finally:
        close_db(db)

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
    if stats['chat_history_size_bytes'] > CHAT_HISTORY_LIMIT * WARNING_THRESHOLD:
        alerts.append({
            'level': 'warning',
            'message': f'Chat history size ({stats["chat_history_size"]}) is approaching the limit of {CHAT_HISTORY_LIMIT / (1024*1024):.2f} MB'
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