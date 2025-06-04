#!/usr/bin/env python3
"""
Auto-delete scheduler for chatbot conversations
Runs daily to check for conversations eligible for deletion and sends notifications
"""

import os
import sys
import datetime
import logging
from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from datetime import timedelta

# Add the current directory to Python path to import models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

# Import models
from models import ChatHistory, ChatbotContent, User, get_db, close_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('auto_delete.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def send_deletion_notification(user_email, user_name, chatbot_name, deletion_date, conversation_count):
    """
    Record deletion notification (actual notification will be shown in chat interface)
    """
    try:
        # Simply log that notification should be shown to user
        logger.info(f"🔔 Will notify in chat: {user_email} ({user_name})")
        logger.info(f"   - Chatbot: {chatbot_name}")
        logger.info(f"   - Conversations to be deleted: {conversation_count}")
        logger.info(f"   - Deletion date: {deletion_date.strftime('%B %d, %Y')}")
        logger.info(f"   - User will see notification in chat interface")
        
        return True
    except Exception as e:
        logger.error(f"Error recording notification for {user_email}: {e}")
        return False

def process_auto_deletions():
    """
    Main function to process auto-deletions and notifications
    """
    db = get_db()
    try:
        logger.info("🚀 Starting auto-deletion processing...")
        
        # Get all active chatbots with auto-delete enabled
        chatbots_with_auto_delete = db.query(ChatbotContent).filter(
            and_(
                ChatbotContent.is_active == True,
                ChatbotContent.auto_delete_days.isnot(None),
                ChatbotContent.auto_delete_days > 0
            )
        ).all()
        
        if not chatbots_with_auto_delete:
            logger.info("ℹ️ No chatbots with auto-delete enabled found.")
            return
        
        logger.info(f"📋 Found {len(chatbots_with_auto_delete)} chatbots with auto-delete enabled")
        
        total_notifications_sent = 0
        total_conversations_deleted = 0
        
        for chatbot in chatbots_with_auto_delete:
            logger.info(f"\n🤖 Processing chatbot: {chatbot.name} (auto-delete: {chatbot.auto_delete_days} days)")
            
            # Calculate cutoff dates
            deletion_cutoff = datetime.datetime.utcnow() - timedelta(days=chatbot.auto_delete_days)
            warning_days = max(3, chatbot.auto_delete_days // 10)  # At least 3 days warning
            warning_cutoff = datetime.datetime.utcnow() - timedelta(days=chatbot.auto_delete_days - warning_days)
            
            logger.info(f"   📅 Deletion cutoff: {deletion_cutoff.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"   ⚠️ Warning cutoff: {warning_cutoff.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 1. Find conversations that need deletion notifications (3 days before deletion)
            conversations_needing_notification = db.query(ChatHistory).filter(
                and_(
                    ChatHistory.program_code == chatbot.code.upper(),
                    ChatHistory.timestamp < warning_cutoff,
                    ChatHistory.timestamp >= deletion_cutoff,  # Not yet eligible for deletion
                    ChatHistory.deletion_notified_at.is_(None),  # Not yet notified
                    ChatHistory.is_visible == True
                )
            ).all()
            
            # Group notifications by user
            user_notifications = {}
            for conversation in conversations_needing_notification:
                if conversation.user_id not in user_notifications:
                    user_notifications[conversation.user_id] = []
                user_notifications[conversation.user_id].append(conversation)
            
            # Send notifications
            for user_id, conversations in user_notifications.items():
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    deletion_date = datetime.datetime.utcnow() + timedelta(days=warning_days)
                    success = send_deletion_notification(
                        user.email, 
                        user.last_name, 
                        chatbot.name,
                        deletion_date,
                        len(conversations)
                    )
                    
                    if success:
                        # Mark conversations as notified
                        for conv in conversations:
                            conv.deletion_notified_at = datetime.datetime.utcnow()
                        total_notifications_sent += 1
                        logger.info(f"   ✅ Notification sent to {user.email} for {len(conversations)} conversations")
            
            # 2. Find conversations eligible for deletion
            conversations_to_delete = db.query(ChatHistory).filter(
                and_(
                    ChatHistory.program_code == chatbot.code.upper(),
                    ChatHistory.timestamp < deletion_cutoff,
                    ChatHistory.is_visible == True
                )
            ).all()
            
            if conversations_to_delete:
                logger.info(f"   🗑️ Found {len(conversations_to_delete)} conversations eligible for deletion")
                
                # Group by user for logging
                user_deletion_counts = {}
                for conv in conversations_to_delete:
                    if conv.user_id not in user_deletion_counts:
                        user_deletion_counts[conv.user_id] = 0
                    user_deletion_counts[conv.user_id] += 1
                
                # Hard delete conversations (permanently remove from database)
                for conversation in conversations_to_delete:
                    db.delete(conversation)
                
                total_conversations_deleted += len(conversations_to_delete)
                
                # Log deletion summary
                for user_id, count in user_deletion_counts.items():
                    user = db.query(User).filter(User.id == user_id).first()
                    if user:
                        logger.info(f"   📝 Permanently deleted {count} conversations for user {user.email}")
            else:
                logger.info(f"   ✅ No conversations found for deletion")
        
        # Commit all changes
        db.commit()
        
        logger.info(f"\n📊 Auto-deletion processing completed:")
        logger.info(f"   📧 Notifications sent: {total_notifications_sent}")
        logger.info(f"   🗑️ Conversations deleted: {total_conversations_deleted}")
        
    except Exception as e:
        logger.error(f"❌ Error in auto-deletion processing: {e}", exc_info=True)
        if db:
            db.rollback()
        raise e
    finally:
        if db:
            close_db(db)

def cleanup_old_notifications():
    """
    Clean up old notification records (older than 1 year)
    Since we now use hard delete, this function removes old notification tracking records
    """
    db = get_db()
    try:
        cutoff_date = datetime.datetime.utcnow() - timedelta(days=365)
        
        # Delete old notification records for conversations that no longer exist
        deleted_count = db.query(ChatHistory).filter(
            and_(
                ChatHistory.deletion_notified_at.isnot(None),
                ChatHistory.deletion_notified_at < cutoff_date
            )
        ).delete()
        
        db.commit()
        logger.info(f"🧹 Cleaned up {deleted_count} old notification records")
        
    except Exception as e:
        logger.error(f"Error in cleanup: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            close_db(db)

def get_auto_delete_statistics():
    """
    Get statistics about auto-delete feature usage
    """
    db = get_db()
    try:
        stats = {}
        
        # Count chatbots with auto-delete enabled
        chatbots_with_auto_delete = db.query(ChatbotContent).filter(
            and_(
                ChatbotContent.is_active == True,
                ChatbotContent.auto_delete_days.isnot(None),
                ChatbotContent.auto_delete_days > 0
            )
        ).count()
        
        # Count total conversations
        total_conversations = db.query(ChatHistory).filter(ChatHistory.is_visible == True).count()
        
        # Count conversations eligible for deletion
        eligible_for_deletion = 0
        for chatbot in db.query(ChatbotContent).filter(
            and_(
                ChatbotContent.is_active == True,
                ChatbotContent.auto_delete_days.isnot(None),
                ChatbotContent.auto_delete_days > 0
            )
        ).all():
            cutoff = datetime.datetime.utcnow() - timedelta(days=chatbot.auto_delete_days)
            count = db.query(ChatHistory).filter(
                and_(
                    ChatHistory.program_code == chatbot.code.upper(),
                    ChatHistory.timestamp < cutoff,
                    ChatHistory.is_visible == True
                )
            ).count()
            eligible_for_deletion += count
        
        stats = {
            'chatbots_with_auto_delete': chatbots_with_auto_delete,
            'total_active_conversations': total_conversations,
            'conversations_eligible_for_deletion': eligible_for_deletion,
            'timestamp': datetime.datetime.utcnow()
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        return None
    finally:
        if db:
            close_db(db)

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 ACSWI Chatbot Auto-Delete Scheduler")
    print("=" * 60)
    
    try:
        # Get statistics before processing
        stats_before = get_auto_delete_statistics()
        if stats_before:
            logger.info(f"📊 Statistics before processing:")
            logger.info(f"   - Chatbots with auto-delete: {stats_before['chatbots_with_auto_delete']}")
            logger.info(f"   - Total conversations: {stats_before['total_active_conversations']}")
            logger.info(f"   - Eligible for deletion: {stats_before['conversations_eligible_for_deletion']}")
        
        # Process auto-deletions
        process_auto_deletions()
        
        # Clean up old notifications monthly (run only on 1st of month)
        if datetime.datetime.utcnow().day == 1:
            logger.info("\n🧹 Running monthly cleanup...")
            cleanup_old_notifications()
        
        # Get statistics after processing
        stats_after = get_auto_delete_statistics()
        if stats_after:
            logger.info(f"\n📊 Statistics after processing:")
            logger.info(f"   - Total conversations: {stats_after['total_active_conversations']}")
            logger.info(f"   - Eligible for deletion: {stats_after['conversations_eligible_for_deletion']}")
        
        print("\n✅ Auto-delete processing completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Auto-delete processing failed: {e}")
        print(f"\n❌ Error: {e}")
        sys.exit(1) 