import openai
import os
import datetime
import smartsheet
import csv
import io
import threading
import logging
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, redirect, url_for, make_response, Response, session, flash, send_file
from functools import wraps
import re
from models import User, ChatbotContent, get_db, close_db, ChatHistory, UserLORootID, ChatbotLORootAssociation
import werkzeug
import glob
import shutil
from werkzeug.utils import secure_filename
import sys
import site
import hashlib
from functools import lru_cache
import numpy as np
from threading import Lock
from sklearn.metrics.pairwise import cosine_similarity
import time
from database_monitor import get_database_size, check_database_limits, setup_database_monitoring
from datetime import datetime, timedelta
import pandas as pd
from io import StringIO, BytesIO
from sqlalchemy import func, and_
import markdown2  # Add markdown2 for markdown parsing
import pytz  # Add pytz for timezone conversion

# Authentication imports
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from flask_bcrypt import Bcrypt
from itsdangerous import URLSafeTimedSerializer

# For file content extraction - try to import, but don't fail if not available
try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

try:
    import textract
    TEXTRACT_AVAILABLE = True
except ImportError:
    TEXTRACT_AVAILABLE = False

try:
    from pptx import Presentation
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialize Flask application
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")  # Add a secret key for session management

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Initialize Flask-Mail
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])

mail = Mail(app)

# Initialize Flask-Bcrypt
bcrypt = Bcrypt(app)

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    db = get_db()
    try:
        user = User.get_by_id(db, int(user_id))
        return user
    except Exception as e:
        logger.error(f"Error loading user {user_id}: {e}")
        return None
    finally:
        close_db(db)

# Authentication helper functions
def generate_reset_token(email):
    """Generate secure reset token for password reset"""
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='password-reset-salt')

def verify_reset_token(token, expiration=3600):
    """Verify reset token (default 1 hour expiration)"""
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token,
            salt='password-reset-salt',
            max_age=expiration
        )
        return email
    except Exception as e:
        logger.debug(f"Token verification failed: {e}")
        return None

def generate_password_setup_token(email):
    """Generate secure token for initial password setup"""
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='password-setup-salt')

def verify_password_setup_token(token, expiration=86400):
    """Verify password setup token (default 24 hours expiration)"""
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token,
            salt='password-setup-salt',
            max_age=expiration
        )
        return email
    except Exception as e:
        logger.debug(f"Password setup token verification failed: {e}")
        return None

def send_password_reset_email(email, name):
    """Send password reset email"""
    try:
        token = generate_reset_token(email)
        reset_url = url_for('reset_password', token=token, _external=True)
        
        msg = Message(
            subject='Password Reset Request',
            recipients=[email]
        )
        
        msg.html = f"""
        <h2>Password Reset Request</h2>
        <p>Hi {name},</p>
        <p>You requested a password reset for your account. Click the link below to reset your password:</p>
        <p><a href="{reset_url}">Reset Password</a></p>
        <p>This link will expire in 1 hour.</p>
        <p>If you didn't request this reset, please ignore this email.</p>
        <p>Best regards,<br>ACS Chatbot System</p>
        """
        
        mail.send(msg)
        logger.info(f"Password reset email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send password reset email to {email}: {e}")
        return False

def send_password_setup_email(email, name, is_admin_added=False):
    """Send initial password setup email"""
    try:
        token = generate_password_setup_token(email)
        setup_url = url_for('setup_password', token=token, _external=True)
        
        msg = Message(
            subject='Set Up Your Account Password',
            recipients=[email]
        )
        
        if is_admin_added:
            intro = f"<p>Hi {name},</p><p>An account has been created for you by an administrator."
        else:
            intro = f"<p>Hi {name},</p><p>Welcome! Your account has been verified."
        
        msg.html = f"""
        <h2>Set Up Your Password</h2>
        {intro} Please set up your password to access the ACS Chatbot System:</p>
        <p><a href="{setup_url}">Set Up Password</a></p>
        <p>This link will expire in 24 hours.</p>
        <p>Once you set up your password, you can log in using your email and password.</p>
        <p>Best regards,<br>ACS Chatbot System</p>
        """
        
        mail.send(msg)
        logger.info(f"Password setup email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send password setup email to {email}: {e}")
        return False

# Add Jinja2 template filter for timezone conversion
@app.template_filter('to_eastern')
def to_eastern_time(dt):
    """Convert datetime to Eastern Time"""
    if dt is None:
        return ''
    
    # Handle string timestamps
    if isinstance(dt, str):
        try:
            # Try to parse common timestamp formats
            dt = dt.strip()
            
            # Handle 'N/A' or empty strings
            if dt in ['N/A', '', 'None', 'null']:
                return ''
            
            # Try different datetime formats
            formats = [
                '%Y-%m-%d %H:%M:%S.%f',  # With microseconds
                '%Y-%m-%d %H:%M:%S',     # Standard format
                '%Y-%m-%d %H:%M',        # Without seconds
                '%Y-%m-%d',              # Date only
                '%m/%d/%Y %H:%M:%S',     # US format with time
                '%m/%d/%Y',              # US date format
            ]
            
            parsed_dt = None
            for fmt in formats:
                try:
                    parsed_dt = datetime.datetime.strptime(dt, fmt)
                    break
                except ValueError:
                    continue
            
            if parsed_dt is None:
                # If all formats fail, return the original string
                return dt
            
            dt = parsed_dt
            
        except Exception as e:
            # If parsing fails, return the original string
            return dt
    
    # If datetime is naive (no timezone info), assume it's UTC
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    
    # Convert to Eastern Time
    eastern = pytz.timezone('US/Eastern')
    eastern_time = dt.astimezone(eastern)
    
    # Format as desired
    return eastern_time.strftime('%Y-%m-%d %H:%M:%S ET')

# Configuration for authorized users CSV file
def get_csv_file_path():
    """Get the appropriate CSV file path based on environment"""
    if os.getenv('RENDER') or os.getenv('RAILWAY_STATIC_URL') or os.getenv('HEROKU_APP_NAME'):
        # In cloud deployment environments, use tmp directory
        csv_dir = '/tmp'
        if not os.path.exists(csv_dir):
            os.makedirs(csv_dir, exist_ok=True)
        return os.path.join(csv_dir, 'authorized_users.csv')
    else:
        # Local development - use app directory
        return os.path.join(os.path.dirname(__file__), 'authorized_users.csv')

AUTHORIZED_USERS_CSV = get_csv_file_path()
authorized_users_cache = {}  # Cache for authorized users
authorized_users_last_modified = None  # Track file modification time

def load_authorized_users():
    """Load authorized users from CSV file with caching"""
    global authorized_users_cache, authorized_users_last_modified
    
    try:
        # Check if file exists
        if not os.path.exists(AUTHORIZED_USERS_CSV):
            logger.warning(f"Authorized users CSV file not found: {AUTHORIZED_USERS_CSV}")
            logger.info("No CSV restriction active - allowing all registrations")
            return {}
        
        # Check file modification time for cache invalidation
        current_mtime = os.path.getmtime(AUTHORIZED_USERS_CSV)
        
        # If cache is empty or file was modified, reload
        if not authorized_users_cache or current_mtime != authorized_users_last_modified:
            logger.info("Loading authorized users from CSV...")
            
            # Read CSV with actual format: user_code,last_name,email,status,class_name,date,lo_root_id
            df = pd.read_csv(AUTHORIZED_USERS_CSV, header=None, names=[
                'user_code', 'last_name', 'email', 'status', 'class_name', 'date', 'lo_root_id'
            ])
            
            # Group by (last_name, email) and collect all lo_root_ids for each user
            new_cache = {}
            active_count = 0
            
            # Group by user (last_name + email combination)
            user_groups = df.groupby(['last_name', 'email'])
            
            for (last_name, email), group in user_groups:
                try:
                    # Clean the data
                    last_name = str(last_name).strip()
                    email = str(email).strip().lower()
                    
                    # Check if any row for this user has 'active' status
                    statuses = group['status'].str.strip().str.lower()
                    is_active = any(status == 'active' for status in statuses)
                    
                    if is_active and last_name and email:
                        # Collect all unique lo_root_ids for this user
                        lo_root_ids = []
                        for lo_root_id in group['lo_root_id']:
                            lo_root_id_clean = str(lo_root_id).strip()
                            if lo_root_id_clean and lo_root_id_clean not in lo_root_ids:
                                lo_root_ids.append(lo_root_id_clean)
                        
                        if lo_root_ids:  # Only add users with at least one lo_root_id
                            key = (last_name.lower(), email)
                            new_cache[key] = {
                                'last_name': last_name,
                                'email': email,
                                'status': 'active',
                                'lo_root_ids': lo_root_ids,  # List of all lo_root_ids
                                'lo_root_id': ';'.join(lo_root_ids)  # Semicolon-separated for backward compatibility
                            }
                            active_count += 1
                            logger.debug(f"Loaded user {last_name} ({email}) with {len(lo_root_ids)} lo_root_ids: {lo_root_ids}")
                            
                except Exception as e:
                    logger.warning(f"Error processing user group {last_name}, {email}: {e}")
                    continue
            
            authorized_users_cache = new_cache
            authorized_users_last_modified = current_mtime
            
            logger.info(f"Loaded {active_count} authorized users from CSV")
            
        return authorized_users_cache
        
    except Exception as e:
        logger.error(f"Error loading authorized users CSV: {e}")
        return {}

def clear_authorized_users_cache():
    """Clear the authorized users cache to force reload"""
    global authorized_users_cache, authorized_users_last_modified
    authorized_users_cache = {}
    authorized_users_last_modified = None

def cleanup_old_csv_backups():
    """Clean up any existing CSV backup files to save space"""
    try:
        csv_dir = os.path.dirname(get_csv_file_path())
        import glob
        
        # Find all backup files
        backup_files = glob.glob(os.path.join(csv_dir, 'authorized_users_backup_*.csv'))
        
        if backup_files:
            deleted_count = 0
            for backup_file in backup_files:
                try:
                    os.remove(backup_file)
                    deleted_count += 1
                    logger.info(f"Deleted backup file: {backup_file}")
                except Exception as e:
                    logger.warning(f"Failed to delete backup {backup_file}: {e}")
            
            if deleted_count > 0:
                logger.info(f"Cleanup complete: {deleted_count} backup files deleted")
        else:
            logger.info("No backup files found to clean up")
            
    except Exception as e:
        logger.error(f"Error during backup cleanup: {e}")

def store_csv_metadata_in_db(db, active_users_count, total_users_count):
    """
    Deprecated: This function has been removed to save space.
    No longer storing CSV metadata.
    """
    pass  # Function removed - no longer needed

def is_user_authorized(last_name, email):
    """Check if user is authorized to register"""
    authorized_users = load_authorized_users()
    
    if not authorized_users:
        logger.warning("No authorized users loaded - allowing registration")
        return True, None  # If no CSV file, allow registration
    
    key = (last_name.lower().strip(), email.lower().strip())
    user_data = authorized_users.get(key)
    
    if user_data:
        logger.info(f"User authorized: {last_name} ({email})")
        return True, user_data
    else:
        logger.info(f"User not authorized: {last_name} ({email})")
        return False, None

def has_chatbot_access(user_id, chatbot_code):
    """Check if a user has access to a specific chatbot based on LO Root IDs"""
    db = get_db()
    try:
        logger.info(f"🔍 DEBUGGING ACCESS: User {user_id} trying to access chatbot {chatbot_code}")
        
        # Get the chatbot and its LO Root IDs
        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            logger.warning(f"📋 Chatbot {chatbot_code} not found")
            return False
        
        # Get chatbot's required LO Root IDs
        chatbot_lo_root_ids = [assoc.lo_root_id for assoc in chatbot.lo_root_ids]
        logger.info(f"📋 Chatbot {chatbot_code} requires LO Root IDs: {chatbot_lo_root_ids}")
        
        # If no LO Root IDs are specified for the chatbot, allow access for all users
        if not chatbot_lo_root_ids:
            logger.info(f"✅ Chatbot {chatbot_code} has no access restrictions - allowing access for user {user_id}")
            return True
        
        # Get user's LO Root IDs
        user = User.get_by_id(db, user_id)
        if not user:
            logger.warning(f"👤 User {user_id} not found")
            return False
        
        user_lo_root_ids = [assoc.lo_root_id for assoc in user.lo_root_ids]
        logger.info(f"👤 User {user_id} ({user.last_name}) has LO Root IDs: {user_lo_root_ids}")
        
        # Check if user has any matching LO Root IDs
        matching_ids = set(user_lo_root_ids) & set(chatbot_lo_root_ids)
        logger.info(f"🔄 Matching IDs found: {matching_ids}")
        
        if matching_ids:
            logger.info(f"✅ ACCESS GRANTED: User {user_id} has access to chatbot {chatbot_code} via LO Root IDs: {matching_ids}")
            return True
        else:
            logger.warning(f"🔄 ACCESS DENIED: User {user_id} denied access to chatbot {chatbot_code}. User LO Root IDs: {user_lo_root_ids}, Required: {chatbot_lo_root_ids}")
            return False
            
    except Exception as e:
        logger.error(f"🔄 ERROR checking chatbot access for user {user_id}, chatbot {chatbot_code}: {e}")
        return False
    finally:
        close_db(db)

# Program content dictionaries (in-memory cache)
program_content = {}
program_names = {}
program_descriptions = {}
deleted_programs = set()  # Keep track of deleted programs temporarily

# Add after other global variables
content_hashes = {}  # Store content hashes for each chatbot

# Embedding caching system
embedding_cache = {}  # Cache for question -> embedding vector
similar_questions_cache = {}  # Cache for question -> similar question mapping
embedding_lock = Lock()  # Lock for thread safety
SIMILARITY_THRESHOLD = 0.85  # Similarity threshold (consider similar if > 0.85)

def get_content_hash(content):
    """Generate a hash for the content to use for caching"""
    return hashlib.md5(content.encode()).hexdigest()

def get_embedding(text):
    """
    Generate OpenAI embedding for the text.
    Results are cached to prevent duplicate API calls for the same text.
    """
    # Basic preprocessing: lowercase, normalize whitespace
    normalized_text = re.sub(r'\s+', ' ', text.lower()).strip()
    
    # Check if embedding already exists in cache
    if normalized_text in embedding_cache:
        logger.debug(f"Embedding cache hit for: {normalized_text[:30]}...")
        return embedding_cache[normalized_text]
    
    try:
        # Call OpenAI embedding API
        response = openai.Embedding.create(
            model="text-embedding-3-small",
            input=normalized_text
        )
        # Ensure embedding is a standard list to avoid method_descriptor errors
        embedding = list(response['data'][0]['embedding'])
        
        # Store in cache
        with embedding_lock:
            embedding_cache[normalized_text] = embedding
            
            # Limit cache size (optional)
            if len(embedding_cache) > 10000:
                # Remove oldest entry
                oldest_key = next(iter(embedding_cache))
                embedding_cache.pop(oldest_key)
        
        logger.debug(f"Generated embedding for: {normalized_text[:30]}...")
        return embedding
    
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        return None

def find_similar_question(user_message, content_hash, chatbot_code):
    """
    Find a question similar to the given user_message.
    Returns a cached question within the chatbot_code that has similarity above threshold.
    """
    # Basic preprocessing: lowercase, normalize whitespace
    normalized_question = re.sub(r'\s+', ' ', user_message.lower()).strip()
    
    # Create cache key specific to this chatbot
    cache_key = f"{chatbot_code}:{normalized_question}"
    
    # Check if we already found similar questions in cache
    if cache_key in similar_questions_cache:
        logger.debug(f"Similar question cache hit for: {normalized_question[:30]}...")
        return similar_questions_cache[cache_key]
    
    # Generate embedding for new question
    new_embedding = get_embedding(normalized_question)
    if new_embedding is None:
        return None
    
    # Construct a list to hold questions from cache keys for this specific chatbot
    content_questions = []
    
    # Get cache info
    cache_info = get_cached_response.cache_info()
    # Extract the cache dictionary
    if hasattr(cache_info, '_cache'):
        cache_dict = cache_info._cache
    else:
        # For some Python versions, it might be just .cache
        cache_dict = get_cached_response.cache
    
    # Find existing questions for this specific chatbot
    for key in cache_dict:
        # key format is now (content_hash, user_message, chatbot_code)
        if len(key) >= 3 and key[0] == content_hash and key[2] == chatbot_code:
            content_questions.append(key[1])  # Extract question part
    
    # Find similar questions
    best_similarity = 0
    best_question = None
    
    for question in content_questions:
        question_embedding = get_embedding(question)
        if question_embedding is None:
            continue
        
        try:
            # Use custom cosine similarity function instead of scikit-learn's
            similarity = custom_cosine_similarity(new_embedding, question_embedding)
            
            # If similarity exceeds threshold and is better than previous best, update
            if similarity >= SIMILARITY_THRESHOLD and similarity > best_similarity:
                best_similarity = similarity
                best_question = question
                logger.debug(f"Found similar question for {chatbot_code}: '{question}' for '{normalized_question}' with similarity {similarity:.3f}")
        except Exception as e:
            logger.error(f"Error calculating similarity between embeddings: {str(e)}")
            continue
    
    # Store in similar questions cache
    similar_questions_cache[cache_key] = best_question
    
    # If we found a similar question, return it
    return best_question

@lru_cache(maxsize=1000)
def get_cached_response(content_hash, user_message, chatbot_code):
    """Get cached response for the same content, user message, and chatbot code.
    This function is decorated with lru_cache which will cache the results,
    reducing API costs by using cached inputs (50% cost reduction).
    Each chatbot maintains its own cache based on its unique code and system prompts.
    """
    # Find program code based on content hash
    if chatbot_code not in program_content:
        logger.error(f"Program content not found for chatbot: {chatbot_code}")
        return None
    
    try:
        # Get actual content to use in system message
        content = program_content[chatbot_code]
        # Try to get system prompt from DB
        db = get_db()
        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        
        system_prompt_role_text = ""
        system_prompt_guidelines_text = ""
        char_limit_value = "50000" # Default character limit if not found

        if chatbot:
            char_limit_value = str(chatbot.char_limit) if chatbot.char_limit else "50000"
            
            program_display_name = program_names.get(chatbot_code, chatbot_code) # Get display name
            system_prompt_role_text = f"You are an assistant that answers questions ONLY based on the provided content for the '{program_display_name}' program. Your primary goal is to act as a knowledgeable expert on this specific content."

            if chatbot.system_prompt_guidelines:
                system_prompt_guidelines_text = chatbot.system_prompt_guidelines.replace("{char_limit}", char_limit_value)
            else: # Fallback to default guidelines if not set
                system_prompt_guidelines_text = f"""1. Only answer questions based on the provided content
2. If the answer is not in the content, say "I don't have enough information to answer that question"
3. Be concise but thorough in your responses
4. Maintain a professional and helpful tone
5. If asked about something not covered in the content, do not make assumptions
6. Preserve ALL important facts, key concepts, definitions, and essential information without exception. The summary should aim for approximately {char_limit_value} characters, but prioritize content preservation over length."""

            # Strengthened instruction for content-only answers
            system_prompt = (
                f"You are an expert assistant for the '{program_display_name}' program. Your primary role is to provide helpful information based on the provided content.\n\n"
                f"{system_prompt_role_text}\n\n"
                f"IMPORTANT GUIDELINES:\n{system_prompt_guidelines_text}\n\n"
                f"RESPONSE APPROACH:\n"
                f"- Answer questions directly related to the provided content\n"
                f"- For application-based or scenario-based questions, use the content as a foundation to provide practical guidance\n"
                f"- You may extrapolate from the content to answer 'how-to' questions, create examples, or provide implementation guidance\n"
                f"- For completely unrelated topics (e.g., cooking, sports, unrelated subjects), respond with 'I don't have enough information to answer that question'\n"
                f"- Focus on being helpful while staying within the domain of the program content\n\n"
                f"CONTENT:\n{content}"
            )
        else:
            # Fallback if chatbot object itself is not found (should be rare)
            default_guidelines = f"""1. Only answer questions based on the provided content
2. If the answer is not in the content, say "I don't have enough information to answer that question"
3. Be concise but thorough in your responses
4. Maintain a professional and helpful tone
5. If asked about something not covered in the content, do not make assumptions
6. Preserve ALL important facts, key concepts, definitions, and essential information without exception. The summary should aim for approximately {char_limit_value} characters, but prioritize content preservation over length."""
            program_display_name = program_names.get(chatbot_code, chatbot_code) # Get display name for fallback
            system_prompt_role_fallback = f"You are an assistant that answers questions ONLY based on the provided content for the '{program_display_name}' program. Your primary goal is to act as a knowledgeable expert on this specific content."
            system_prompt = (
                f"You are an expert assistant for the '{program_display_name}' program. Your primary role is to provide helpful information based on the provided content.\n\n"
                f"{system_prompt_role_fallback}\n\n"
                f"IMPORTANT GUIDELINES:\n{default_guidelines}\n\n"
                f"RESPONSE APPROACH:\n"
                f"- Answer questions directly related to the provided content\n"
                f"- For application-based or scenario-based questions, use the content as a foundation to provide practical guidance\n"
                f"- You may extrapolate from the content to answer 'how-to' questions, create examples, or provide implementation guidance\n"
                f"- For completely unrelated topics (e.g., cooking, sports, unrelated subjects), respond with 'I don't have enough information to answer that question'\n"
                f"- Focus on being helpful while staying within the domain of the program content\n\n"
                f"CONTENT:\n{content}"
            )
        
        close_db(db)
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=1500,  # Increased from 500 to 1500
            temperature=0.3   # Added for more creative responses
        )
        
        # Get the response content
        response_content = response['choices'][0]['message']['content'].strip()
        
        # Check if response was cut off and try to complete it naturally
        if response['choices'][0]['finish_reason'] == 'length':
            logger.warning(f"Response was truncated due to token limit for question: {user_message[:50]}...")
            
            try:
                # Try to complete the response with a shorter follow-up
                completion_response = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": f"{system_prompt}\n\nIMPORTANT: Complete this response naturally and concisely. Provide a proper conclusion."},
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": response_content},
                        {"role": "user", "content": "Please complete your previous response with a brief conclusion."}
                    ],
                    max_tokens=300,  # Shorter completion
                    temperature=0.3
                )
                
                completion_text = completion_response['choices'][0]['message']['content'].strip()
                
                # Combine original response with completion
                if completion_text and not completion_text.lower().startswith(('sorry', 'i cannot', 'i don\'t have')):
                    response_content = response_content + " " + completion_text
                else:
                    # If completion failed, add a natural ending
                    response_content = response_content + "\n\n[Response continues with additional details available in the program content]"
            except Exception as completion_error:
                logger.error(f"Error completing truncated response: {str(completion_error)}")
                # Add a natural ending if completion fails
                response_content = response_content + "\n\n[Response continues with additional details available in the program content]"
        
        return response_content
        
    except Exception as e:
        logger.error(f"Error getting cached response: {str(e)}")
        return None

# Load content summaries for each program from database
def load_program_content():
    # Clear existing content
    program_content.clear()
    program_names.clear()
    program_descriptions.clear()
    deleted_programs.clear()
    content_hashes.clear()  # Clear content hashes
    
    # Get all active chatbot contents from database
    db = get_db()
    try:
        # Get only active chatbots
        chatbots = db.query(ChatbotContent).filter(ChatbotContent.is_active == True).all()
        
        # Load content into memory
        for chatbot in chatbots:
            program_content[chatbot.code] = chatbot.content
            program_names[chatbot.code] = chatbot.name
            program_descriptions[chatbot.code] = chatbot.description or ""
            # Store content hash for caching
            content_hash_value = get_content_hash(chatbot.content)
            content_hashes[chatbot.code] = content_hash_value
            logger.info(f"Loaded chatbot '{chatbot.code}': Name='{chatbot.name}', Content Length={len(chatbot.content)}, Hash={content_hash_value}")
        
        # Make sure default programs are defined with proper names even if not in DB
        default_programs = {
            "BCC": "Building Coaching Competency",
            "MI": "Motivational Interviewing",
            "Safety": "Safety and Risk Assessment"
        }
        
        for code, name in default_programs.items():
            if code not in program_names:
                program_names[code] = name
        
        logger.info(f"Loaded {len(program_content)} program content entries from database")
        logger.debug(f"Available programs: {', '.join(program_content.keys())}")
        logger.debug(f"Content hashes generated for caching: {', '.join(content_hashes.keys())}")
        
        # Clear cached responses when content is reloaded to ensure new prompts take effect
        get_cached_response.cache_clear()
        logger.info("Cleared cached responses to apply updated system prompts")
    finally:
        close_db(db)

# Function to migrate existing file-based content to database
def migrate_content_to_db():
    db = get_db()
    try:
        # Find all content summary files
        summary_files = glob.glob("content_summary_*.txt")
        migrated_count = 0
        
        for file_path in summary_files:
            # Extract program name from filename
            program_code = file_path.replace("content_summary_", "").replace(".txt", "").upper()
            
            # Skip if already in database
            existing = ChatbotContent.get_by_code(db, program_code)
            if existing:
                logger.debug(f"Program {program_code} already in database, skipping")
                continue
                
            # Read content
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Get description from memory or use default
                display_name = program_names.get(program_code, program_code)
                description = program_descriptions.get(program_code, "")
                
                # Create database entry
                ChatbotContent.create_or_update(
                    db, 
                    code=program_code, 
                    name=display_name,
                    content=content, 
                    description=description
                )
                migrated_count += 1
                
            except Exception as e:
                logger.error(f"Error migrating program {program_code}: {str(e)}")
        
        # Commit changes
        if migrated_count > 0:
            db.commit()
            logger.info(f"Migrated {migrated_count} program content files to database")
    finally:
        close_db(db)

# Initialize program content
load_program_content()

# Basic Auth settings
AUTHORIZED_USERNAME = os.getenv("AUTH_USERNAME")  # default: admin
AUTHORIZED_PASSWORD = os.getenv("AUTH_PASSWORD")  # default: password

def check_auth(username, password):
    """Check if a username/password combination is valid."""
    return username == AUTHORIZED_USERNAME and password == AUTHORIZED_PASSWORD

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# Decorator to require login for general user routes
def login_required(f):
    """Custom login required decorator that works with Flask-Login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'info')
            return redirect(url_for('login_page', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# --- Smartsheet Integration Setup ---
SMARTSHEET_ACCESS_TOKEN = os.getenv("SMARTSHEET_ACCESS_TOKEN")
SMARTSHEET_SHEET_ID = os.getenv("SMARTSHEET_SHEET_ID")
SMARTSHEET_TIMESTAMP_COLUMN = os.getenv("SMARTSHEET_TIMESTAMP_COLUMN")
SMARTSHEET_QUESTION_COLUMN = os.getenv("SMARTSHEET_QUESTION_COLUMN")
SMARTSHEET_RESPONSE_COLUMN = os.getenv("SMARTSHEET_RESPONSE_COLUMN")

if SMARTSHEET_TIMESTAMP_COLUMN:
    SMARTSHEET_TIMESTAMP_COLUMN = int(SMARTSHEET_TIMESTAMP_COLUMN)
if SMARTSHEET_QUESTION_COLUMN:
    SMARTSHEET_QUESTION_COLUMN = int(SMARTSHEET_QUESTION_COLUMN)
if SMARTSHEET_RESPONSE_COLUMN:
    SMARTSHEET_RESPONSE_COLUMN = int(SMARTSHEET_RESPONSE_COLUMN)

smartsheet_client = None
if SMARTSHEET_ACCESS_TOKEN:
    smartsheet_client = smartsheet.Smartsheet(SMARTSHEET_ACCESS_TOKEN)

def record_in_smartsheet(user_question, chatbot_reply):
    """
    Record the user's question and chatbot response in Smartsheet.
    Adds a new row with the current timestamp, the user's question,
    and the chatbot's reply.
    """
    if not smartsheet_client or not SMARTSHEET_SHEET_ID:
        return

    new_row = smartsheet.models.Row()
    new_row.to_top = True
    new_row.cells = [
        {
            'column_id': SMARTSHEET_TIMESTAMP_COLUMN,
            'value': datetime.now().isoformat()
        },
        {
            'column_id': SMARTSHEET_QUESTION_COLUMN,
            'value': user_question
        },
        {
            'column_id': SMARTSHEET_RESPONSE_COLUMN,
            'value': chatbot_reply
        }
    ]
    response = smartsheet_client.Sheets.add_rows(SMARTSHEET_SHEET_ID, [new_row])
    return response
# --- End of Smartsheet Integration Setup ---

# Home route: redirect to login page
@app.route('/')
def home():
    if 'user_id' in session:  # Check if a regular user session exists
        return redirect(url_for('program_select'))
    return redirect(url_for('login'))

# Registration route - Step 1: Verify credentials
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        
        if not last_name or not email:
            flash("Last name and email are required.", "danger")
            return redirect(url_for('register'))
        
        # Check if user is authorized to register
        is_authorized, user_data = is_user_authorized(last_name, email)
        
        if not is_authorized:
            logger.warning(f"Unauthorized registration attempt: {last_name} ({email})")
            flash("Registration is restricted. Please contact an administrator if you believe this is an error.", "danger")
            return redirect(url_for('register'))
        
        db = get_db()
        try:
            # Check if user already exists
            existing_user = User.get_by_credentials(db, last_name, email)
            if existing_user:
                if existing_user.has_password():
                    flash("User already exists. Please try logging in instead.", "warning")
                    close_db(db)
                    return redirect(url_for('login_page'))
                else:
                    # User exists but no password set - send setup email
                    send_password_setup_email(email, last_name)
                    flash("Password setup email sent! Please check your email to set up your password.", "info")
                    close_db(db)
                    return redirect(url_for('login_page'))
            
            # Store registration data in session for step 2
            session['registration_data'] = {
                'last_name': last_name,
                'email': email,
                'user_data': user_data
            }
            
            close_db(db)
            return redirect(url_for('register_password'))
            
        except Exception as e:
            db.rollback()
            logger.error("Registration error: %s", str(e))
            close_db(db)
            flash("Registration error occurred. Please try again.", "danger")
            return redirect(url_for('register'))
            
    return render_template('register.html')

# Registration route - Step 2: Set password
@app.route('/register/password', methods=['GET', 'POST'])
def register_password():
    if 'registration_data' not in session:
        flash("Registration session expired. Please start again.", "warning")
        return redirect(url_for('register'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash("Both password fields are required.", "danger")
            return render_template('register_password.html')
        
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template('register_password.html')
        
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return render_template('register_password.html')
        
        # Get registration data from session
        reg_data = session['registration_data']
        last_name = reg_data['last_name']
        email = reg_data['email']
        user_data = reg_data['user_data']
        
        db = get_db()
        try:
            # Create new user with password
            expiry_date = datetime.utcnow() + timedelta(days=2*365)
            new_user = User(
                last_name=last_name, 
                email=email,
                status='Active',
                date_added=datetime.utcnow(),
                expiry_date=expiry_date
            )
            new_user.set_password(password)
            db.add(new_user)
            db.flush()  # Get the user ID
            
            # Add lo_root_ids from CSV data if available
            if user_data and user_data.get('lo_root_ids'):
                lo_root_ids = user_data['lo_root_ids']
                logger.debug(f"Adding lo_root_ids for new user {last_name}: {lo_root_ids}")
                for lr_id in lo_root_ids:
                    if lr_id:
                        user_lo_association = UserLORootID(user_id=new_user.id, lo_root_id=lr_id)
                        db.add(user_lo_association)
            
            db.commit()
            logger.info(f"User {last_name} ({email}) registered successfully with password")
            
            # Clear registration session data
            session.pop('registration_data', None)
            
            flash("Registration successful! You can now log in with your email and password.", "success")
            close_db(db)
            return redirect(url_for('login_page'))
            
        except Exception as e:
            db.rollback()
            logger.error("Registration password setup error: %s", str(e))
            close_db(db)
            flash("Registration error occurred. Please try again.", "danger")
            return redirect(url_for('register'))
            
    reg_data = session.get('registration_data', {})
    return render_template('register_password.html', 
                         last_name=reg_data.get('last_name', ''),
                         email=reg_data.get('email', ''))

# Login route - Email + Password
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    # If already logged in, redirect to program_select
    if current_user.is_authenticated:
        return redirect(url_for('program_select'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))
        
        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template('login.html')
        
        db = get_db()
        try:
            user = User.get_by_email(db, email)
            
            if not user:
                flash("Invalid email or password.", "danger")
                close_db(db)
                return render_template('login.html')
            
            if not user.has_password():
                flash("Password not set. Please check your email for password setup instructions.", "warning")
                close_db(db)
                return render_template('login.html')
            
            if not user.check_password(password):
                # Check if this is a scrypt hash compatibility issue
                if user.password_hash and user.password_hash.startswith('scrypt:'):
                    flash("Your password needs to be reset due to a system update. Please use 'Forgot Password?' to reset it.", "warning")
                else:
                    flash("Invalid email or password.", "danger")
                close_db(db)
                return render_template('login.html')
            
            # Update visit count
            user.visit_count += 1
            db.commit()
            
            # Log in user with Flask-Login
            login_user(user, remember=remember)
            logger.info(f"User {user.email} logged in successfully")
            
            close_db(db)
            
            # Redirect to next page or program selection
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('program_select'))
                
        except Exception as e:
            db.rollback()
            close_db(db)
            logger.error("Login error: %s", str(e))
            flash("Login error occurred. Please try again.", "danger")
            return render_template('login.html')
            
    return render_template('login.html')

# Legacy login route (for backward compatibility)
@app.route('/login_legacy', methods=['GET', 'POST'])
def login():
    return redirect(url_for('login_page'))

# First-time password setup for existing users
@app.route('/first-time-password', methods=['GET', 'POST'])
def first_time_password():
    if request.method == 'POST':
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        
        if not last_name or not email:
            flash("Last name and email are required.", "danger")
            return render_template('first_time_password.html')
        
        db = get_db()
        try:
            user = User.get_by_credentials(db, last_name, email)
            
            if user and not user.has_password():
                # Send password setup email
                if send_password_setup_email(email, last_name):
                    flash("Password setup email sent! Please check your email.", "success")
                else:
                    flash("Failed to send email. Please try again later.", "danger")
            else:
                # Don't reveal if user exists or already has password for security
                flash("If your account exists and needs password setup, an email has been sent.", "info")
            
            close_db(db)
            return redirect(url_for('login_page'))
            
        except Exception as e:
            close_db(db)
            logger.error("First-time password error: %s", str(e))
            flash("An error occurred. Please try again.", "danger")
            return render_template('first_time_password.html')
    
    return render_template('first_time_password.html')

# Forgot password route
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        
        if not email:
            flash("Email is required.", "danger")
            return render_template('forgot_password.html')
        
        db = get_db()
        try:
            user = User.get_by_email(db, email)
            
            if user and user.has_password():
                # Send password reset email
                if send_password_reset_email(email, user.last_name):
                    flash("Password reset email sent! Please check your email.", "success")
                else:
                    flash("Failed to send email. Please try again later.", "danger")
            else:
                # Don't reveal if user exists for security
                flash("If your account exists, a password reset email has been sent.", "info")
            
            close_db(db)
            return redirect(url_for('login_page'))
            
        except Exception as e:
            close_db(db)
            logger.error("Forgot password error: %s", str(e))
            flash("An error occurred. Please try again.", "danger")
            return render_template('forgot_password.html')
    
    return render_template('forgot_password.html')

# Password reset route
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    email = verify_reset_token(token)
    if not email:
        flash("Invalid or expired reset link.", "danger")
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash("Both password fields are required.", "danger")
            return render_template('reset_password.html')
        
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template('reset_password.html')
        
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return render_template('reset_password.html')
        
        db = get_db()
        try:
            user = User.get_by_email(db, email)
            if user:
                user.set_password(password)
                db.commit()
                logger.info(f"Password reset successful for {email}")
                flash("Password reset successful! You can now log in.", "success")
                close_db(db)
                return redirect(url_for('login_page'))
            else:
                flash("User not found.", "danger")
                close_db(db)
                return redirect(url_for('forgot_password'))
                
        except Exception as e:
            db.rollback()
            close_db(db)
            logger.error("Password reset error: %s", str(e))
            flash("An error occurred. Please try again.", "danger")
            return render_template('reset_password.html')
    
    return render_template('reset_password.html')

# Password setup route (for new users and admin-added users)
@app.route('/setup-password/<token>', methods=['GET', 'POST'])
def setup_password(token):
    email = verify_password_setup_token(token)
    if not email:
        flash("Invalid or expired setup link.", "danger")
        return redirect(url_for('first_time_password'))
    
    db = get_db()
    try:
        user = User.get_by_email(db, email)
        if not user:
            flash("User not found.", "danger")
            close_db(db)
            return redirect(url_for('register'))
        
        if user.has_password():
            flash("Password already set. Please use the login page.", "info")
            close_db(db)
            return redirect(url_for('login_page'))
        
        if request.method == 'POST':
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            
            if not password or not confirm_password:
                flash("Both password fields are required.", "danger")
                return render_template('setup_password.html', user=user)
            
            if password != confirm_password:
                flash("Passwords do not match.", "danger")
                return render_template('setup_password.html', user=user)
            
            if len(password) < 8:
                flash("Password must be at least 8 characters long.", "danger")
                return render_template('setup_password.html', user=user)
            
            # Set password
            user.set_password(password)
            db.commit()
            logger.info(f"Password setup successful for {email}")
            
            flash("Password set successfully! You can now log in.", "success")
            close_db(db)
            return redirect(url_for('login_page'))
        
        close_db(db)
        return render_template('setup_password.html', user=user)
        
    except Exception as e:
        db.rollback()
        close_db(db)
        logger.error("Password setup error: %s", str(e))
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('first_time_password'))

# Program selection route
@app.route('/program_select')
@login_required
def program_select():
    # Verify user is logged in (handled by decorator)
    user_id = current_user.id
    user = current_user  # Get current user object
    
    # Get all available programs from database
    db = get_db()
    try:
        chatbots = ChatbotContent.get_all_active(db)
        
        available_programs = []
        available_program_codes = []
        
        for chatbot in chatbots:
            # Check if user has access to this chatbot
            if has_chatbot_access(user_id, chatbot.code):
                # Determine if NEW badge should be shown
                show_new = False
                if chatbot.created_at:
                    # Show NEW if created within the last 14 days (changed from 7 days)
                    if (datetime.now() - chatbot.created_at).days < 14:
                        show_new = True
                
                # Ensure predefined programs BCC, MI, Safety do not show 'NEW' badge
                if chatbot.code in ['BCC', 'MI', 'SAFETY']:
                    show_new = False

                program_info = {
                    "code": chatbot.code,
                    "name": chatbot.name,
                    "description": chatbot.description or f"Learn about the {chatbot.name} program content.",
                    "show_new_badge": show_new,
                    "category": chatbot.category or "standard"  # Include category, default to standard
                }
                available_programs.append(program_info)
                available_program_codes.append(chatbot.code)
            else:
                logger.debug(f"User {user_id} does not have access to chatbot {chatbot.code}")
        
        available_programs.sort(key=lambda x: x["name"])
        
        logger.info(f"Program select page for user: {user_id}, showing {len(available_programs)} accessible programs out of {len(chatbots)} total")
        return render_template('program_select.html', 
                              available_programs=available_programs,
                              available_program_codes=available_program_codes,
                              current_user=user)  # Pass current_user to template
    finally:
        close_db(db)

# Set program route
@app.route('/set_program/<program>')
@login_required
def set_program(program):
    # Verify if content exists for this program in the database
    user_id = current_user.id
    
    db = get_db()
    try:
        chatbot = ChatbotContent.get_by_code(db, program.upper())
        if not chatbot or not chatbot.is_active:
            logger.warning(f"Attempt to access non-existent program: {program}")
            close_db(db)
            return redirect(url_for('program_select'))
        
        # Check if user has access to this chatbot
        if not has_chatbot_access(user_id, program.upper()):
            logger.warning(f"User {user_id} denied access to chatbot {program.upper()} - insufficient LO Root ID permissions")
            flash(f"Access denied: You don't have permission to access the {chatbot.name} program.", "danger")
            close_db(db)
            return redirect(url_for('program_select'))
            
        logger.debug("Setting program %s for user %s", program, user_id)
        
        # Get user by ID
        user = User.get_by_id(db, user_id)
        
        if not user:
            logger.warning("User not found in database")
            close_db(db)
            # Clear session and redirect to login
            logout_user()
            return redirect(url_for('login'))
            
        # Get lo_root_ids for the chatbot
        chatbot_lo_root_ids = [assoc.lo_root_id for assoc in chatbot.lo_root_ids]
        
        # Add lo_root_ids to user if they don't already have them
        existing_lo_root_ids = [assoc.lo_root_id for assoc in user.lo_root_ids]
        for lo_root_id in chatbot_lo_root_ids:
            if lo_root_id not in existing_lo_root_ids:
                new_assoc = UserLORootID(user_id=user.id, lo_root_id=lo_root_id)
                db.add(new_assoc)
        
        # Set in session for current view
        session['current_program'] = program.upper()
        
        # Commit changes
        db.commit()
        
        # Fix variable name
        program_upper = program.upper()
        
        logger.info(f"User {user_id} successfully accessed chatbot {program_upper}")
        
        # Cleanup
        close_db(db)
        
        # Redirect to the appropriate program page
        if program_upper == "BCC":
            return redirect(url_for('index_bcc'))
        elif program_upper == "MI":
            return redirect(url_for('index_mi'))
        elif program_upper == "SAFETY":
            return redirect(url_for('index_safety'))
        else:
            # For custom programs, use the generic index route
            return redirect(url_for('index_generic', program=program))
        
    except Exception as e:
        # Rollback on error
        db.rollback()
        close_db(db)
        logger.error("Error setting program: %s", str(e))
        return redirect(url_for('program_select'))

# Helper: fetch chat history for a user and program and calculate remaining questions
def get_chat_history_and_remaining(user_id, program_code, limit=50):
    db = get_db()
    try:
        # Get chat history
        history = db.query(ChatHistory).filter(
            ChatHistory.user_id == user_id,
            ChatHistory.program_code == program_code,
            ChatHistory.is_visible == True
        ).order_by(ChatHistory.timestamp.asc()).limit(limit).all()
        
        result = []
        for h in history:
            # Get deletion info for this chat
            deletion_info = get_chat_deletion_info(h.timestamp, program_code)
            
            # Add user message
            user_msg = {
                'message': h.user_message,
                'sender': 'user',
                'timestamp': h.timestamp.strftime('%Y-%m-%d %H:%M')
            }
            if deletion_info:
                user_msg['deletion_info'] = deletion_info
            result.append(user_msg)
            
            # Add bot message
            bot_msg = {
                'message': h.bot_message,
                'sender': 'bot',
                'timestamp': h.timestamp.strftime('%Y-%m-%d %H:%M')
            }
            if deletion_info:
                bot_msg['deletion_info'] = deletion_info
            result.append(bot_msg)
        
        # Calculate remaining questions for today
        chatbot = ChatbotContent.get_by_code(db, program_code)
        quota = chatbot.quota if chatbot else 3
        
        # Count today's messages for this user and program using UTC consistently
        from datetime import timezone
        today_utc = datetime.now(timezone.utc).date()
        today_start_utc = datetime.combine(today_utc, datetime.min.time()).replace(tzinfo=timezone.utc)
        today_end_utc = datetime.combine(today_utc, datetime.max.time()).replace(tzinfo=timezone.utc)
        
        logger.info(f"get_chat_history_and_remaining: Checking quota for user {user_id}, program {program_code}, date range: {today_start_utc} to {today_end_utc}")
        
        message_count = db.query(ChatHistory).filter(
            ChatHistory.user_id == user_id,
            ChatHistory.program_code == program_code,
            ChatHistory.timestamp >= today_start_utc,
            ChatHistory.timestamp <= today_end_utc
        ).count()
        
        remaining_questions = max(0, quota - message_count)
        
        logger.info(f"get_chat_history_and_remaining: User {user_id} in program {program_code} has {message_count}/{quota} messages today, {remaining_questions} remaining")
        
        return result, remaining_questions, quota
    finally:
        close_db(db)

# BCC Chatbot interface
@app.route('/index_bcc')
@login_required
def index_bcc():
    user_id = current_user.id
    
    # Check access for BCC program
    if not has_chatbot_access(user_id, 'BCC'):
        flash("You don't have access to this chatbot program.", "error")
        return redirect(url_for('program_select'))
    
    chat_history, remaining_quota, quota = get_chat_history_and_remaining(user_id, 'BCC')
    deletion_warning = get_deletion_warning_for_user(user_id, 'BCC')
    intro_message = get_intro_message('BCC')
    
    return render_template('index.html',
                         program_display_name="Building Coaching Competency",
                         program_code="BCC",
                         intro_message=intro_message,
                         chat_history=chat_history,
                         remaining_questions=remaining_quota,
                         quota=quota,
                         current_user=current_user,
                         deletion_warning=deletion_warning)

# MI Chatbot interface
@app.route('/index_mi')
@login_required
def index_mi():
    user_id = current_user.id
    
    # Check access for MI program
    if not has_chatbot_access(user_id, 'MI'):
        flash("You don't have access to this chatbot program.", "error")
        return redirect(url_for('program_select'))
    
    chat_history, remaining_quota, quota = get_chat_history_and_remaining(user_id, 'MI')
    deletion_warning = get_deletion_warning_for_user(user_id, 'MI')
    intro_message = get_intro_message('MI')
    
    return render_template('index.html',
                         program_display_name="Motivational Interviewing",
                         program_code="MI",
                         intro_message=intro_message,
                         chat_history=chat_history,
                         remaining_questions=remaining_quota,
                         quota=quota,
                         current_user=current_user,
                         deletion_warning=deletion_warning)

# Safety Chatbot interface
@app.route('/index_safety')
@login_required
def index_safety():
    user_id = current_user.id
    
    # Check access for Safety program
    if not has_chatbot_access(user_id, 'S&R'):
        flash("You don't have access to this chatbot program.", "error")
        return redirect(url_for('program_select'))
    
    chat_history, remaining_quota, quota = get_chat_history_and_remaining(user_id, 'S&R')
    deletion_warning = get_deletion_warning_for_user(user_id, 'S&R')
    intro_message = get_intro_message('S&R')
    
    return render_template('index.html',
                         program_display_name="Safety and Risk",
                         program_code="S&R",
                         intro_message=intro_message,
                         chat_history=chat_history,
                         remaining_questions=remaining_quota,
                         quota=quota,
                         current_user=current_user,
                         deletion_warning=deletion_warning)

# Generic chatbot interface for custom programs
@app.route('/index_generic/<program>')
@login_required
def index_generic(program):
    # Check if user has access to this program
    user_id = current_user.id
    if not has_chatbot_access(user_id, program):
        flash("You don't have access to this chatbot program.", "error")
        return redirect(url_for('program_select'))
    
    # Check if the program exists in our chatbot content
    if program not in program_content:
        flash(f"Program '{program}' not found.", "error")
        return redirect(url_for('program_select'))
    
    # Get chat history and quota information
    chat_history, remaining_quota, quota = get_chat_history_and_remaining(user_id, program)
    
    # Check for deletion warning
    deletion_warning = get_deletion_warning_for_user(user_id, program)
    
    # Get the intro message for this program
    intro_message = get_intro_message(program)
    
    # Load all available chatbots for the sidebar
    all_available_chatbots = []
    db = get_db()
    try:
        # Get all active chatbots from database instead of using program_content
        active_chatbots = db.query(ChatbotContent).filter(ChatbotContent.is_active == True).all()
        for chatbot in active_chatbots:
            if has_chatbot_access(user_id, chatbot.code):
                all_available_chatbots.append({
                    'code': chatbot.code,
                    'name': chatbot.name,
                    'category': chatbot.category or 'standard'
                })
    finally:
            close_db(db)
    
    # Get the current program's name from database
    db = get_db()
    try:
        current_chatbot = ChatbotContent.get_by_code(db, program)
        program_display_name = current_chatbot.name if current_chatbot else program
    finally:
        close_db(db)
        
    return render_template(
        'index.html', 
                            program_display_name=program_display_name,
        program_code=program,
                            chat_history=chat_history,
        remaining_questions=remaining_quota,
                            quota=quota,
        intro_message=intro_message,
        current_user=current_user,
        deletion_warning=deletion_warning
    )

# Legacy index route - redirect to program selection
@app.route('/index')
def index():
    # If somehow users reach this route, redirect to program selection
    logger.debug("Redirecting from legacy index route to program selection")
    return redirect(url_for('program_select'))

def parse_markdown(text):
    """
    Convert markdown text to HTML with additional features.
    """
    extras = [
        'fenced-code-blocks',  # Support for ```code blocks```
        'tables',              # Support for markdown tables
        'break-on-newline',    # Convert newlines to <br>
        'header-ids',          # Add IDs to headers
        'markdown-in-html',    # Allow markdown inside HTML
        'target-blank-links',  # Open links in new tab
        'task_list',          # Support for GitHub-style task lists
        'footnotes',          # Support for footnotes
        'strike',             # Support for ~~strikethrough~~
        'underline',          # Support for _underline_
        'highlight',          # Support for ==highlighted text==
    ]
    
    # Convert markdown to HTML
    html = markdown2.markdown(text, extras=extras)
    
    # Add custom styling for code blocks
    html = html.replace('<pre><code>', '<pre><code class="language-plaintext">')
    
    return html

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_id = current_user.id
    user_message = request.json.get('message')
    current_program = session.get('current_program')

    if not user_message:
        return jsonify({"error": "Message is required"}), 400

    if not current_program:
        logger.error(f"No current program set for user {user_id}")
        return jsonify({"error": "No program selected. Please select a program first."}), 400

    db = get_db()
    try:
        # Get the chatbot's quota from database
        chatbot = ChatbotContent.get_by_code(db, current_program)
        if not chatbot:
            return jsonify({"error": "Program not found."}), 404
        
        quota = chatbot.quota
        logger.info(f"User {user_id} attempting to send message. Program: {current_program}, Quota: {quota}")

        # Count today's messages for this user and program using UTC consistently
        from datetime import timezone
        today_utc = datetime.now(timezone.utc).date()
        today_start_utc = datetime.combine(today_utc, datetime.min.time()).replace(tzinfo=timezone.utc)
        today_end_utc = datetime.combine(today_utc, datetime.max.time()).replace(tzinfo=timezone.utc)
        
        logger.info(f"Checking quota for user {user_id}, program {current_program}, date range: {today_start_utc} to {today_end_utc}")
        
        # Use a database transaction to prevent race conditions
        message_count = db.query(ChatHistory).filter(
            ChatHistory.user_id == user_id,
            ChatHistory.program_code == current_program,
            ChatHistory.timestamp >= today_start_utc,
            ChatHistory.timestamp <= today_end_utc
        ).count()
        
        logger.info(f"Current message count for user {user_id} in program {current_program}: {message_count}/{quota}")

        if message_count >= quota:
            logger.warning(f"User {user_id} has reached quota limit for {current_program}: {message_count}/{quota}")
            return jsonify({"reply": f"You have reached your daily quota of {quota} questions for the {chatbot.name} program. Please try again tomorrow."}), 200

        content_hash = content_hashes.get(current_program)
        if not content_hash:
            # This block should ideally not be hit if load_program_content works correctly after chatbot creation
            content_for_hash = program_content.get(current_program, "")
            if not content_for_hash:
                logger.error(f"CRITICAL: Content for program '{current_program}' is MISSING from program_content dict in /chat endpoint.")
                # Attempt to reload all program content as a fallback, though this indicates a deeper issue
                load_program_content() 
                content_for_hash = program_content.get(current_program, "") # Try again
                if not content_for_hash:
                     logger.error(f"CRITICAL: Content for '{current_program}' STILL MISSING after reload. Chatbot will not function.")
                     return jsonify({"reply": "I apologize, but I'm currently unable to access my knowledge base for this program. Please try again later or contact an administrator."}), 500
            
            content_hash = get_content_hash(content_for_hash)
            content_hashes[current_program] = content_hash
            logger.warning(f"Re-generated content hash for '{current_program}' in /chat endpoint. This might indicate an issue if it happens frequently for existing chatbots.")
        else:
            logger.info(f"Successfully retrieved content_hash for '{current_program}' in /chat endpoint: {content_hash}")

        # Verify content is available before calling get_cached_response
        current_program_content = program_content.get(current_program)
        if not current_program_content:
            logger.error(f"CRITICAL: Content for '{current_program}' is NOT FOUND in program_content when preparing for get_cached_response. Hash was {content_hash}")
            load_program_content() # Attempt reload
            current_program_content = program_content.get(current_program)
            if not current_program_content:
                logger.error(f"CRITICAL: Content for '{current_program}' STILL MISSING after reload in /chat. Cannot proceed.")
                return jsonify({"reply": "I apologize, but I'm having trouble accessing the content for this program. Please contact an administrator."}), 500
            logger.info(f"Content for '{current_program}' was reloaded. Length: {len(current_program_content)}")
        else:
            logger.info(f"Content for '{current_program}' (length: {len(current_program_content)}) is available for get_cached_response.")

        start_time = time.time()
        cache_result = "exact_match"
        
        chatbot_reply = get_cached_response(content_hash, user_message, current_program)
        
        if not chatbot_reply:
            cache_result = "semantic_match"
            try:
                similar_question = find_similar_question(user_message, content_hash, current_program)
                if similar_question:
                    logger.debug(f"Using semantically similar question: '{similar_question}' instead of '{user_message}'")
                    chatbot_reply = get_cached_response(content_hash, similar_question, current_program)
                    logger.debug(f"Retrieved response for semantically similar question in {time.time() - start_time:.3f} seconds")
            except Exception as e:
                logger.error(f"Error finding similar question: {str(e)}")
                similar_question = None
        
        if not chatbot_reply:
            cache_result = "cache_miss"
            try:
                logger.debug(f"Cache miss for {current_program}, getting new response")
                # Use system prompt from DB if available
                if chatbot and chatbot.system_prompt_role and chatbot.system_prompt_guidelines:
                    system_prompt = f"{chatbot.system_prompt_role}\n\nIMPORTANT GUIDELINES:\n{chatbot.system_prompt_guidelines}\n\nCONTENT:\n{program_content.get(current_program, '')}"
                else:
                    system_prompt = f"""You are an assistant that answers questions based on the following content for the {program_names.get(current_program, 'selected')} program.

IMPORTANT GUIDELINES:
1. Only answer questions based on the provided content
2. If the answer is not in the content, say "I don't have enough information to answer that question"
3. Be concise but thorough in your responses
4. Maintain a professional and helpful tone
5. If asked about something not covered in the content, do not make assumptions

CONTENT:
{program_content.get(current_program, '')}"""
                response = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    max_tokens=1500,  # Increased from 500 to 1500
                    temperature=0.3   # Added for more creative responses
                )
                chatbot_reply = response['choices'][0]['message']['content'].strip()
                
                # Check if response was cut off and try to complete it naturally
                if response['choices'][0]['finish_reason'] == 'length':
                    logger.warning(f"Response was truncated due to token limit for question: {user_message[:50]}...")
                    
                    try:
                        # Try to complete the response with a shorter follow-up
                        completion_response = openai.ChatCompletion.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role": "system", "content": f"{system_prompt}\n\nIMPORTANT: Complete this response naturally and concisely. Provide a proper conclusion."},
                                {"role": "user", "content": user_message},
                                {"role": "assistant", "content": chatbot_reply},
                                {"role": "user", "content": "Please complete your previous response with a brief conclusion."}
                            ],
                            max_tokens=300,  # Shorter completion
                            temperature=0.3
                        )
                        
                        completion_text = completion_response['choices'][0]['message']['content'].strip()
                        
                        # Combine original response with completion
                        if completion_text and not completion_text.lower().startswith(('sorry', 'i cannot', 'i don\'t have')):
                            chatbot_reply = chatbot_reply + " " + completion_text
                        else:
                            # If completion failed, add a natural ending
                            chatbot_reply = chatbot_reply + "\n\n[Response continues with additional details available in the program content]"
                    except Exception as completion_error:
                        logger.error(f"Error completing truncated response: {str(completion_error)}")
                        # Add a natural ending if completion fails
                        chatbot_reply = chatbot_reply + "\n\n[Response continues with additional details available in the program content]"
            except Exception as e:
                logger.error(f"Error getting new response: {str(e)}")
                return jsonify({"error": str(e)}), 500
        
        total_time = time.time() - start_time
        logger.info(f"Cache performance: {cache_result} in {total_time:.3f} seconds")

        # Parse markdown in the response
        html_reply = parse_markdown(chatbot_reply)

        # Save to chat history with UTC timestamp
        chat_entry = ChatHistory(
            user_id=user_id,
            program_code=current_program,
            user_message=user_message,
            bot_message=chatbot_reply,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None)  # Store as UTC without timezone info
        )
        db.add(chat_entry)
        db.commit()
        
        logger.info(f"Successfully saved chat entry for user {user_id} in program {current_program}")

        # Record conversation in Smartsheet asynchronously
        def record_smartsheet_async(user_question, chatbot_reply, program):
            try:
                record_in_smartsheet(f"[{program}] {user_question}", chatbot_reply)
            except Exception as smex:
                logger.error("Error recording in Smartsheet: %s", str(smex))

        threading.Thread(target=record_smartsheet_async, args=(user_message, chatbot_reply, current_program)).start()

        # Calculate remaining questions after this interaction
        remaining_questions = max(0, quota - (message_count + 1))
        
        logger.info(f"Interaction complete. User {user_id} has {remaining_questions} questions remaining for {current_program}")

        return jsonify({
            "reply": chatbot_reply,
            "html_reply": html_reply,
            "remaining_questions": remaining_questions,
            "quota": quota
        })

    except Exception as e:
        if 'db' in locals():
            db.rollback()
        logger.error(f"Error in chat endpoint: {str(e)}")
        return jsonify({"error": "An error occurred while processing your request. Please try again."}), 500
    finally:
        close_db(db)

@app.route('/clear_chat_history', methods=['POST'])
@login_required
def clear_chat_history():
    user_id = current_user.id
    # Ensure program_code is fetched from the request body, not session, for robustness
    data = request.get_json()
    program_code = data.get('program')

    if not program_code:
        logger.error("Program code not provided in clear_chat_history request.")
        return jsonify({'success': False, 'error': 'Program code is required.'}), 400

    db = get_db()
    try:
        # Hide all messages for the given user_id and program_code by setting is_visible=False
        # This version clears all history for the program, not just today's.
        # If only today's history should be cleared, revert to the date-based logic.
        updated_rows = db.query(ChatHistory).filter(
            ChatHistory.user_id == user_id,
            ChatHistory.program_code == program_code,
            ChatHistory.is_visible == True
        ).update({ChatHistory.is_visible: False}, synchronize_session=False)
        
        db.commit()
        logger.info(f"Cleared {updated_rows} chat history entries for user {user_id} in program {program_code}.")
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing chat history for user {user_id}, program {program_code}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        close_db(db)

# Program switch route
@app.route('/switch_program')
@login_required
def switch_program():
    return redirect(url_for('program_select'))

# Logout route
@app.route('/logout')
def logout():
    logout_user()  # Flask-Login logout
    flash('Successfully logged out.', 'success')
    return redirect(url_for('login_page'))

# Delete Registration Route
@app.route('/delete_registration', methods=['GET', 'POST'])
@requires_auth
def delete_registration():
    if request.method == 'GET':
        return render_template('delete_registration.html')
    
    data = request.get_json(silent=True)
    if data is None:
        data = request.form

    email = data.get('email')
    last_name = data.get('last_name')

    if not email or not last_name:
        return "Email and Last Name are required to delete registration.", 400

    email = email.strip()
    last_name = last_name.strip()

    db = get_db()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            db.delete(user)
            db.commit()
            message = "Your registration has been successfully removed."
            status_code = 200
        else:
            message = "User not found. No registration to remove."
            status_code = 404
        close_db(db)
        return message, status_code
    except Exception as e:
        db.rollback()
        message = f"Error during deletion: {str(e)}"
        status_code = 500
        close_db(db)
        return message, status_code

@app.route('/export_users', methods=['GET'])
@requires_auth
def export_users():
    """Export all users to CSV."""
    # Create CSV in memory
    si = StringIO()
    cw = csv.writer(si)
    
    # Write header
    cw.writerow(['ID', 'Last Name', 'Email', 'Visit Count', 'Status', 'Date Added', 'Expiry Date', 'LO Root IDs'])
    
    # Get all users
    users = get_all_users()
    
    # Write user data
    for user in users:
        cw.writerow([
            user['id'],
            user['last_name'],
            user['email'],
            user['visit_count'],
            user['status'],
            user['date_added'],
            user['expiry_date'],
            ', '.join(user['lo_root_ids']) if user['lo_root_ids'] else 'None'
        ])
    
    # Create the response
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=users.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/users')
@requires_auth
def show_users():
    db = get_db()
    try:
        # Get all users and convert to dictionaries
        users = db.query(User).all()
        user_data = [user.to_dict() for user in users]
        
        # Convert dictionaries to User-like objects for the template
        class UserObj:
            def __init__(self, data):
                self.id = data['id']
                self.last_name = data['last_name']
                self.email = data['email']
                self.visit_count = data['visit_count']
                self.status = data['status']
                self.date_added = data['date_added']
                self.expiry_date = data['expiry_date']
                self.lo_root_ids = data['lo_root_ids']
                
        user_objects = [UserObj(data) for data in user_data]
        close_db(db)
        return render_template('users.html', users=user_objects)
    except Exception as e:
        logger.error("Error showing users: %s", str(e))
        close_db(db)
        return f"Error showing users: {str(e)}", 500

@app.route('/export')
@requires_auth
def export_page():
    # Add admin page to the routes available from export page
    return render_template('export.html', show_admin_link=True)

def get_paired_conversations(db, page=1, per_page=10):
    # 최신순 정렬
    history_query = db.query(ChatHistory).order_by(ChatHistory.timestamp.desc())
    total_count = history_query.count()
    total_pages = (total_count + per_page - 1) // per_page
    offset = (page - 1) * per_page
    history = history_query.offset(offset).limit(per_page * 10).all()
    paired_conversations = []
    
    # 각 대화 기록을 처리
    for i in range(min(len(history), per_page)):
        current_msg = history[i]
        user_obj = db.query(User).filter(User.id == current_msg.user_id).first()
        chatbot_obj = db.query(ChatbotContent).filter(ChatbotContent.code == current_msg.program_code).first()
        
        user_name = user_obj.last_name if user_obj else 'Unknown'
        user_email = user_obj.email if user_obj else 'Unknown'
        chatbot_name_display = chatbot_obj.name if chatbot_obj else current_msg.program_code
        
        pair_data = {
            'user_id': current_msg.user_id,  # Include user_id for filtering
            'user_timestamp': current_msg.timestamp if current_msg.timestamp else 'N/A',
            'user_name': user_name,
            'user_email': user_email,
            'chatbot_name': chatbot_name_display,
            'user_message': current_msg.user_message,
            'bot_timestamp': current_msg.timestamp if current_msg.timestamp else 'N/A',
            'bot_message': current_msg.bot_message
        }
        
        paired_conversations.append(pair_data)
        
    return paired_conversations, total_pages, page

@app.route('/admin')
@requires_auth
def admin():
    db = get_db()
    try:
        available_chatbots = get_available_chatbots()
        deleted_chatbots = get_deleted_chatbots()
        db_stats = get_database_size()
        alerts = check_database_limits()
        
        # For Data Management Tab - User List
        users_list = get_all_users() 

        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        # For Data Management Tab - Paired Conversation Logs
        paired_conversations_log, total_pages, current_page = get_paired_conversations(
            db, page=page, per_page=per_page
        )

        conversation_stats_overall = get_conversation_statistics() # General stats
        top_users_list = get_top_users(limit=5)
        top_chatbots_list = get_top_chatbots(limit=5)
        
        message = request.args.get('message')
        message_type = request.args.get('message_type', 'info')
        
        # Search/filter parameters from URL for conversation logs
        search_term_param = request.args.get('search_term', None)
        chatbot_code_param = request.args.get('chatbot_code', None)
        user_id_param = request.args.get('user_id', None)

        # If search parameters are present, filter the conversations
        if search_term_param or chatbot_code_param or user_id_param:
            temp_filtered_convos = []
            for p_conv in paired_conversations_log:
                match_search = True
                if search_term_param and not (search_term_param.lower() in p_conv['user_message'].lower() or search_term_param.lower() in p_conv['bot_message'].lower()):
                    match_search = False
                
                match_chatbot = True
                if chatbot_code_param:
                    is_correct_chatbot = False
                    for cb in available_chatbots:
                        if cb['code'] == chatbot_code_param and p_conv['chatbot_name'] == cb['name']:
                            is_correct_chatbot = True
                            break
                    if not is_correct_chatbot:
                         match_chatbot = False
                
                match_user = True
                if user_id_param:
                    # Match by user ID
                    if str(p_conv['user_id']) != str(user_id_param):
                        match_user = False

                if match_search and match_chatbot and match_user:
                    temp_filtered_convos.append(p_conv)
            paired_conversations_log = temp_filtered_convos
            
        return render_template('admin.html', 
                              available_chatbots=available_chatbots, 
                              deleted_chatbots=deleted_chatbots,
                              message=message,
                              message_type=message_type,
                              db_stats=db_stats,
                              alerts=alerts,
                              users=users_list,
                              conversations=paired_conversations_log,
                              conversation_stats=conversation_stats_overall,
                              top_users=top_users_list,
                              top_chatbots=top_chatbots_list,
                              search_term=search_term_param,
                              selected_chatbot_code=chatbot_code_param,
                              selected_user_id=user_id_param,
                              pagination={
                                  'total_pages': total_pages,
                                  'current_page': current_page,
                                  'per_page': per_page
                              })
    finally:
        close_db(db)

@app.route('/admin/export_data')
@requires_auth
def admin_export_data():
    export_type = request.args.get('type', 'users')
    format_type = request.args.get('format', 'csv')
    db = None # Initialize db to None
    try:
        db = get_db() # Get db session
        data = []
        filename_base = "data_export"
        df_columns = []

        if export_type == 'users':
            users_data = get_all_users() # This function should use its own db session
            if not users_data:
                flash("No user data to export.", "warning")
                return redirect(url_for('admin'))
            data = users_data
            filename_base = 'users_export'
            if data: df_columns = list(data[0].keys())

        elif export_type == 'conversations':
            # For export, we use get_recent_conversations which returns individual messages
            # and has its own db session management.
            # Fetch all conversations for export
            all_conversations_flat = get_recent_conversations(limit=db.query(ChatHistory).count())
            if not all_conversations_flat:
                flash("No conversation data to export.", "warning")
                return redirect(url_for('admin'))
            data = all_conversations_flat
            filename_base = 'conversations_export'
            if data: df_columns = list(data[0].keys())
        
        else:
            flash(f"Invalid export type: {export_type}", "danger")
            return redirect(url_for('admin'))

        if not data: # Double check after specific type processing
            flash(f"No data available to export for {export_type}.", "warning")
            return redirect(url_for('admin'))
            
        df = pd.DataFrame(data, columns=df_columns)
        
        output_stream = BytesIO() # Use BytesIO for binary data like Excel
        
        if format_type == 'csv':
            # For CSV, pandas can write to a text wrapper around BytesIO or directly to StringIO
            # Using StringIO for to_csv for consistency with previous text-based output
            csv_output = StringIO()
            df.to_csv(csv_output, index=False)
            output_stream = BytesIO(csv_output.getvalue().encode('utf-8')) # Encode to bytes for Response
            mimetype = "text/csv"
            filename = f"{filename_base}.csv"
        elif format_type == 'excel':
            df.to_excel(output_stream, index=False, sheet_name=export_type)
            # output_stream.seek(0) # Not needed here as to_excel writes and BytesIO is ready
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"{filename_base}.xlsx"
        else:
            flash(f"Invalid export format: {format_type}", "danger")
            return redirect(url_for('admin'))
        
        output_stream.seek(0) # Reset stream position to the beginning
        
        return Response(
            output_stream.getvalue(), # getvalue() from BytesIO
            mimetype=mimetype,
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Error during data export ({export_type}, {format_type}): {str(e)}", exc_info=True)
        flash(f"An error occurred during export: {str(e)}", "danger")
        return redirect(url_for('admin')) # Redirect to admin on error
    finally:
        if db: # Only close if db was successfully obtained
            close_db(db)

@app.route('/admin/search_conversations', methods=['POST'])
@requires_auth
def admin_search_conversations():
    """Search conversations with filters"""
    search_term = request.form.get('search_term', '')
    chatbot = request.form.get('chatbot', '')
    user_email = request.form.get('user_email', '')
    date_from = request.form.get('date_from', '')
    date_to = request.form.get('date_to', '')
    
    db = get_db()
    try:
        query = db.query(ChatHistory)
        
        if search_term:
            query = query.filter(
                # 검색어를 user_message 또는 bot_message에서 찾습니다
                db.or_(
                    ChatHistory.user_message.ilike(f'%{search_term}%'),
                    ChatHistory.bot_message.ilike(f'%{search_term}%')
                )
            )
        if chatbot:
            query = query.filter(ChatHistory.program_code == chatbot)
        if user_email:
            user = db.query(User).filter(User.email == user_email).first()
            if user:
                query = query.filter(ChatHistory.user_id == user.id)
        if date_from:
            query = query.filter(ChatHistory.timestamp >= datetime.strptime(date_from, '%Y-%m-%d'))
        if date_to:
            query = query.filter(ChatHistory.timestamp <= datetime.strptime(date_to, '%Y-%m-%d'))
        
        conversations = query.order_by(ChatHistory.timestamp.desc()).limit(100).all()
        
        result = []
        for conv in conversations:
            user = db.query(User).filter(User.id == conv.user_id).first()
            chatbot = db.query(ChatbotContent).filter(ChatbotContent.code == conv.program_code).first()
            
            # Add user message
            result.append({
                'id': conv.id,
                'user_name': user.last_name if user else 'Unknown',
                'user_email': user.email if user else 'Unknown',
                'chatbot_name': chatbot.name if chatbot else conv.program_code,
                'message': conv.user_message,
                'sender': 'user',
                'timestamp': conv.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
            
            # Add bot message
            result.append({
                'id': conv.id,
                'user_name': user.last_name if user else 'Unknown',
                'user_email': user.email if user else 'Unknown',
                'chatbot_name': chatbot.name if chatbot else conv.program_code,
                'message': conv.bot_message,
                'sender': 'bot',
                'timestamp': conv.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({"success": True, "conversations": result})
        
    finally:
        close_db(db)

@app.route('/admin/delete_conversations', methods=['POST'])
@requires_auth
def admin_delete_conversations():
    """Delete conversations based on specified criteria"""
    delete_type = request.form.get('delete_type')
    
    if not delete_type:
        flash('Invalid request: delete type not specified', 'danger')
        return redirect(url_for('admin', message='Invalid request: delete type not specified', message_type='danger'))
    
    db = get_db()
    try:
        # Count number of records before deletion for reporting
        total_records_before = db.query(ChatHistory).count()
        
        if delete_type == 'all':
            # Delete all conversations from database
            db.query(ChatHistory).delete()
            db.commit()
            deleted_count = total_records_before
            message = f'All {deleted_count} conversation records have been permanently deleted'
            
        elif delete_type == 'by_chatbot':
            chatbot_code = request.form.get('chatbot_code')
            if not chatbot_code:
                flash('Please select a chatbot', 'warning')
                return redirect(url_for('admin', message='Please select a chatbot', message_type='warning'))
            
            # Get chatbot name for reporting
            chatbot = db.query(ChatbotContent).filter(ChatbotContent.code == chatbot_code).first()
            chatbot_name = chatbot.name if chatbot else chatbot_code
            
            # Delete matching records
            deleted_count = db.query(ChatHistory).filter(ChatHistory.program_code == chatbot_code).count()
            db.query(ChatHistory).filter(ChatHistory.program_code == chatbot_code).delete()
            db.commit()
            message = f'All {deleted_count} conversation records for "{chatbot_name}" have been permanently deleted'
            
        elif delete_type == 'by_user':
            user_id = request.form.get('user_id')
            if not user_id:
                flash('Please select a user', 'warning')
                return redirect(url_for('admin', message='Please select a user', message_type='warning'))
            
            # Get user info for reporting
            user = db.query(User).filter(User.id == user_id).first()
            user_name = f"{user.last_name} ({user.email})" if user else f"User ID {user_id}"
            
            # Delete matching records
            deleted_count = db.query(ChatHistory).filter(ChatHistory.user_id == user_id).count()
            db.query(ChatHistory).filter(ChatHistory.user_id == user_id).delete()
            db.commit()
            message = f'All {deleted_count} conversation records for "{user_name}" have been permanently deleted'
            
        else:
            flash(f'Invalid delete type: {delete_type}', 'danger')
            return redirect(url_for('admin', message=f'Invalid delete type: {delete_type}', message_type='danger'))
        
        # Success message
        flash(message, 'success')
        return redirect(url_for('admin', message=message, message_type='success') + '#data-mgmt-content-convo-logs')
        
    except Exception as e:
        logger.error(f"Error deleting conversations ({delete_type}): {str(e)}", exc_info=True)
        db.rollback()
        flash(f'An error occurred while deleting conversations: {str(e)}', 'danger')
        return redirect(url_for('admin', message=f'Error: {str(e)}', message_type='danger'))
    finally:
        close_db(db)

def get_available_chatbots():
    """Get all active chatbots from the database."""
    db = get_db()
    try:
        chatbots = db.query(ChatbotContent).filter(ChatbotContent.is_active == True).all()
        result = []
        for chatbot in chatbots:
            # Get LO Root IDs for this chatbot
            lo_root_ids = [assoc.lo_root_id for assoc in chatbot.lo_root_ids]
            
            chatbot_data = {
                "code": chatbot.code,
                "name": chatbot.name,
                "display_name": chatbot.name,
                "description": chatbot.description or "",
                "quota": chatbot.quota,
                "intro_message": chatbot.intro_message,
                "lo_root_ids": lo_root_ids,  # Add LO Root IDs for admin display
                "category": chatbot.category or "standard",
                "auto_delete_days": chatbot.auto_delete_days  # 👈 NEW: Add auto-delete setting
            }
            result.append(chatbot_data)
        return result
    finally:
        close_db(db)

def get_deleted_chatbots():
    """Get all inactive/deleted chatbots from the database."""
    db = get_db()
    try:
        chatbots = db.query(ChatbotContent).filter(ChatbotContent.is_active == False).all()
        return [
            {
                "code": chatbot.code,
                "name": chatbot.name,
                "display_name": chatbot.name,
                "description": chatbot.description or "",
                "quota": chatbot.quota,
                "intro_message": chatbot.intro_message
            } for chatbot in chatbots
        ]
    finally:
        close_db(db)

# Helper functions for admin page
def get_all_users():
    """Get all users from the database."""
    db = get_db()
    try:
        from sqlalchemy.orm import joinedload
        # Explicitly load the lo_root_ids relationship to avoid lazy loading issues
        users = db.query(User).options(joinedload(User.lo_root_ids)).all()
        
        result = []
        for user in users:
            user_dict = user.to_dict()
            # Debug log to verify lo_root_ids are being loaded correctly
            logger.debug(f"User {user.last_name} ({user.email}) has lo_root_ids: {user_dict['lo_root_ids']}")
            result.append(user_dict)
        
        return result
    finally:
        close_db(db)

def get_recent_conversations(limit=100):
    """Get recent conversations from the database, formatting timestamp."""
    db = get_db()
    try:
        conversations = db.query(ChatHistory).order_by(ChatHistory.timestamp.desc()).limit(limit).all()
        result = []
        for conv in conversations:
            user = db.query(User).filter(User.id == conv.user_id).first()
            chatbot_content = db.query(ChatbotContent).filter(ChatbotContent.code == conv.program_code).first() # Renamed for clarity
            
            # Add user message
            result.append({
                'id': conv.id,
                'user_id': conv.user_id,
                'user_name': user.last_name if user else 'Unknown',
                'user_email': user.email if user else 'Unknown',
                'chatbot_name': chatbot_content.name if chatbot_content else conv.program_code,
                'message': conv.user_message,
                'sender': 'user',
                'timestamp': conv.timestamp.strftime('%Y-%m-%d %H:%M:%S') if conv.timestamp else 'N/A'
            })
            
            # Add bot message
            result.append({
                'id': conv.id,
                'user_id': conv.user_id,
                'user_name': user.last_name if user else 'Unknown',
                'user_email': user.email if user else 'Unknown',
                'chatbot_name': chatbot_content.name if chatbot_content else conv.program_code,
                'message': conv.bot_message,
                'sender': 'bot',
                'timestamp': conv.timestamp.strftime('%Y-%m-%d %H:%M:%S') if conv.timestamp else 'N/A'
            })
        return result
    finally:
        close_db(db)

def get_conversation_statistics():
    """Get conversation statistics."""
    db = get_db()
    try:
        total_conversations = db.query(ChatHistory).count()
        unique_users = db.query(ChatHistory.user_id).distinct().count()
        unique_chatbots = db.query(ChatHistory.program_code).distinct().count()
        
        # Find most active chatbot
        chatbot_counts = db.query(
            ChatHistory.program_code, 
            func.count(ChatHistory.id).label('count')
        ).group_by(ChatHistory.program_code).order_by(func.count(ChatHistory.id).desc()).first()
        
        most_active_chatbot = chatbot_counts[0] if chatbot_counts else "None"
        
        return {
            "total_conversations": total_conversations,
            "unique_users": unique_users,
            "active_chatbots": unique_chatbots,
            "most_active_chatbot": most_active_chatbot
        }
    finally:
        close_db(db)

def get_top_users(limit=5):
    """Get the most active users."""
    db = get_db()
    try:
        # Count messages per user
        user_counts = db.query(
            ChatHistory.user_id,
            func.count(ChatHistory.id).label('message_count')
        ).group_by(ChatHistory.user_id).order_by(func.count(ChatHistory.id).desc()).limit(limit).all()
        
        result = []
        for user_id, message_count in user_counts:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                # Count distinct conversations
                conversation_count = db.query(ChatHistory.program_code).filter(
                    ChatHistory.user_id == user_id
                ).distinct().count()
                
                result.append({
                    "name": user.last_name,
                    "email": user.email,
                    "conversation_count": conversation_count,
                    "message_count": message_count
                })
        
        return result
    finally:
        close_db(db)

def get_top_chatbots(limit=5):
    """Get the most used chatbots."""
    db = get_db()
    try:
        # Count messages per chatbot
        chatbot_counts = db.query(
            ChatHistory.program_code,
            func.count(ChatHistory.id).label('message_count')
        ).group_by(ChatHistory.program_code).order_by(func.count(ChatHistory.id).desc()).limit(limit).all()
        
        result = []
        for program_code, message_count in chatbot_counts:
            chatbot = db.query(ChatbotContent).filter(ChatbotContent.code == program_code).first()
            
            # Count distinct conversations
            conversation_count = db.query(ChatHistory.user_id).filter(
                ChatHistory.program_code == program_code
            ).distinct().count()
            
            result.append({
                "display_name": chatbot.name if chatbot else program_code,
                "conversation_count": conversation_count,
                "message_count": message_count
            })
        
        return result
    finally:
        close_db(db)

# Helper function to extract text from uploaded files
def extract_text_from_file(file_storage):
    """Extracts text from a FileStorage object."""
    filename = secure_filename(file_storage.filename)
    # file_storage.stream is a file-like object (e.g., SpooledTemporaryFile)
    
    logger.debug(f"Attempting to extract text from: {filename}")

    content = ""
    try:
        if filename.endswith(".txt"):
            content = file_storage.stream.read().decode("utf-8")
        elif filename.endswith(".pdf"):
            if PYPDF2_AVAILABLE:
                pdf_reader = PyPDF2.PdfReader(file_storage.stream)
                text_parts = [page.extract_text() or "" for page in pdf_reader.pages]
                content = "\\n".join(text_parts)
            else:
                logger.warning("PyPDF2 not available for PDF extraction.")
        elif filename.endswith(".docx"):
            if DOCX_AVAILABLE:
                doc = docx.Document(file_storage.stream)
                content = "\\n".join([para.text for para in doc.paragraphs])
            elif TEXTRACT_AVAILABLE: # Fallback to textract if python-docx not available
                file_storage.stream.seek(0) # Reset stream for textract
                content = textract.process(filename=filename, input_stream=file_storage.stream).decode('utf-8')
            else:
                logger.warning("Neither python-docx nor textract available for DOCX extraction.")
        elif filename.endswith(".pptx"):
            if PPTX_AVAILABLE:
                prs = Presentation(file_storage.stream)
                text_parts = []
                for slide in prs.slides:
                    for shape in slide.shapes:
                        if hasattr(shape, "text"):
                            text_parts.append(shape.text)
                content = "\\n".join(text_parts)
            elif TEXTRACT_AVAILABLE: # Fallback to textract
                file_storage.stream.seek(0) # Reset stream for textract
                content = textract.process(filename=filename, input_stream=file_storage.stream).decode('utf-8')
            else:
                logger.warning("Neither python-pptx nor textract available for PPTX extraction.")
        else:
            logger.warning(f"Unsupported file type for text extraction: {filename}")
        
        # Ensure stream is reset if it's going to be read again (e.g. multiple calls or other processing)
        file_storage.stream.seek(0)
        return content

    except Exception as e:
        logger.error(f"Error extracting text from {filename}: {e}", exc_info=True)
        # Ensure stream is reset even on error if possible
        try:
            file_storage.stream.seek(0)
        except:
            pass # Stream might be closed or unseekable
        return ""

# Somewhere in the smart_text_summarization function, add a function to proportionally distribute content
def distribute_content_to_files(original_files, combined_content):
    """Distribute the summarized combined content back to individual files proportionally."""
    # If no files or empty combined content, nothing to do
    if not original_files or not combined_content:
        return original_files

    # Calculate total original length
    total_original_length = sum(len(f['content']) for f in original_files)
    
    # If total length is 0, we can't distribute proportionally
    if total_original_length == 0:
        return original_files
    
    # Calculate new total length
    new_total_length = len(combined_content)
    
    # Make a copy of the files list
    updated_files = []
    
    # Keep track of content already assigned
    content_assigned = 0
    
    # For each file except the last one
    for i, file in enumerate(original_files[:-1]):
        # Calculate proportion
        original_proportion = len(file['content']) / total_original_length
        
        # Calculate new length for this file
        new_length = int(new_total_length * original_proportion)
        
        # Slice the content for this file
        if i == 0:  # First file
            file_content = combined_content[:new_length]
        else:  # Middle files
            file_content = combined_content[content_assigned:content_assigned + new_length]
        
        # Update the file
        updated_file = file.copy()
        updated_file['content'] = file_content
        updated_file['char_count'] = len(file_content)
        updated_files.append(updated_file)
        
        # Update content assigned
        content_assigned += new_length
    
    # Add the last file with remaining content to avoid rounding errors
    if original_files:
        last_file = original_files[-1].copy()
        last_file['content'] = combined_content[content_assigned:]
        last_file['char_count'] = len(last_file['content'])
        updated_files.append(last_file)
    
    return updated_files

@app.route('/admin/preview_upload', methods=['POST'])
@requires_auth
def admin_preview_upload():
    """Handles file uploads for previewing content before chatbot creation."""
    try:
        logger.info("admin_preview_upload called")
        
        if 'files' not in request.files and 'current_content' not in request.form:
            logger.warning("No files or content provided for preview")
            return jsonify({"success": False, "error": "No files or content provided for preview."}), 400

        char_limit = int(request.form.get('char_limit', 50000))
        auto_summarize = request.form.get('auto_summarize', 'true').lower() == 'true'
        
        logger.info(f"Preview settings - char_limit: {char_limit}, auto_summarize: {auto_summarize}")
        
        # For edit modal scenario or direct summarization
        current_content_text = request.form.get('current_content', '')
        if current_content_text:
            logger.info(f"Current content provided with length: {len(current_content_text)}")
            
        append_content_flag = request.form.get('append_content', 'false').lower() == 'true'
        logger.info(f"Append content flag: {append_content_flag}")

        extracted_files_data = []
        combined_text_parts = []

        if append_content_flag and current_content_text:
            combined_text_parts.append(current_content_text)
            logger.info(f"Added current content to text parts ({len(current_content_text)} chars)")

        # Only process files if they were provided
        if 'files' in request.files:
            files = request.files.getlist('files')
            logger.info(f"Processing {len(files)} files for preview")
            
            for file_storage in files:
                if file_storage and file_storage.filename:
                    try:
                        text = extract_text_from_file(file_storage)
                        logger.info(f"Extracted {len(text)} chars from {file_storage.filename}")
                        
                        extracted_files_data.append({
                            "filename": secure_filename(file_storage.filename),
                            "content": text,
                            "char_count": len(text)
                        })
                        combined_text_parts.append(text)
                    except Exception as e:
                        logger.error(f"Error extracting text from {file_storage.filename}: {str(e)}")
                        return jsonify({"success": False, "error": f"Error processing file {file_storage.filename}: {str(e)}"}), 500
                else:
                    logger.warning("Empty file storage object received in preview_upload.")
        elif current_content_text:
            # If only current_content was provided (direct summarization)
            logger.info("Using only current_content (no files)")
            combined_text_parts = [current_content_text]

        # Combine all text parts
        combined_preview_content = "\n\n".join(combined_text_parts)
        total_char_count = len(combined_preview_content)
        
        logger.info(f"Combined preview content length: {total_char_count}, char_limit: {char_limit}")
        
        # Check if content exceeds character limit
        exceeds_limit = total_char_count > char_limit
        was_summarized = False
        summarization_result = {"original_length": total_char_count, "final_length": total_char_count, "percent_reduced": 0}
        warning_message = ""

        # Apply summarization if enabled and needed
        if exceeds_limit and auto_summarize:
            logger.info(f"Content exceeds limit, applying summarization (auto_summarize={auto_summarize})")
            
            # Store the original content length before summarization
            original_content_length = total_char_count

            # Calculate tokens and cost first
            estimated_tokens = original_content_length / 4  # Rough estimate: 4 chars per token
            output_tokens = original_content_length / 4  # Rough estimate: 4 chars per token
            input_cost = (estimated_tokens / 1_000_000) * 0.15  # $0.15 per 1M input tokens
            output_cost = (output_tokens / 1_000_000) * 0.60  # $0.60 per 1M output tokens
            estimated_cost = input_cost + output_cost

            # Show API usage cost warning to the admin BEFORE summarization
            pre_warning = ""
            if original_content_length > 10000:
                pre_warning = f"Warning: Summarizing this content with GPT-4o-mini may cost approximately ${estimated_cost:.2f} (input: {estimated_tokens:.0f} tokens, output: {output_tokens:.0f} tokens). Proceeding will use your OpenAI API quota."
                logger.info(pre_warning)
                warning_message = pre_warning  # Show this warning before summarization
            
            # Show API usage cost warning to the admin
            api_usage_warning = ""
            estimated_tokens = original_content_length / 4  # Rough estimate: 4 chars per token
            estimated_cost = (estimated_tokens / 1_000_000) * 0.15  # $0.15 per 1M input tokens
            output_tokens = original_content_length / 4  # Rough estimate: 4 chars per token
            output_cost = (output_tokens / 1_000_000) * 0.60  # $0.60 per 1M output tokens
            estimated_cost = estimated_cost + output_cost
            if original_content_length > 10000:  # Only show warning for larger content
                api_usage_warning = f"Note: Using GPT-4o-mini for summarization will cost approximately ${estimated_cost:.2f} for this content."
                logger.info(f"Showing API cost warning: ${estimated_cost:.2f} for {estimated_tokens:.0f} input tokens, {output_tokens:.0f} output tokens")
                
            # Apply GPT summarization with fallback to rule-based summarization
            combined_preview_content, percent_reduced = gpt_summarize_text(
                combined_preview_content, 
                target_length=int(char_limit * 0.95), 
                max_length=char_limit
            )
            
            # Update the total character count after summarization
            final_content_length = len(combined_preview_content)
            total_char_count = final_content_length
            
            # Check if summarization reduced content
            if final_content_length < original_content_length:
                was_summarized = True
                
                summarization_result = {
                    "original_length": original_content_length,
                    "final_length": final_content_length,
                    "percent_reduced": percent_reduced
                }
                
                logger.info(f"Content summarized: {original_content_length} -> {final_content_length} chars ({percent_reduced}%)")
                
                warning_message = f"Content was automatically summarized to fit within the {char_limit:,} character limit. " \
                                f"Original: {original_content_length:,} characters, Final: {final_content_length:,} characters " \
                                f"({percent_reduced}% reduced). {api_usage_warning}"
                
                # Update the individual file contents using our distribution function
                if extracted_files_data:
                    logger.info("Distributing summarized content back to individual files proportionally")
                    extracted_files_data = distribute_content_to_files(extracted_files_data, combined_preview_content)
                    logger.info(f"Successfully distributed content to {len(extracted_files_data)} files")
            else:
                logger.warning("Summarization did not reduce content length")
                warning_message = "Automatic summarization could not reduce the content further. Manual editing may be required."
                exceeds_limit = total_char_count > char_limit
        elif exceeds_limit:
            logger.info("Content exceeds limit but auto-summarize is disabled")
            warning_message = f"Content exceeds the {char_limit:,} character limit (current: {total_char_count:,} characters). " \
                            f"Enable auto-summarize or reduce content manually."

        # If there was an error or no summarization was needed, return appropriate message
        if not was_summarized and 'current_content' in request.form and not 'files' in request.files:
            logger.info("Direct summarization request handling")
            # This was a direct summarization request that didn't result in summarization
            if exceeds_limit:
                # Content still exceeds limit but no summarization occurred
                logger.warning("Content still exceeds limit but could not be automatically summarized")
                return jsonify({
                    "success": False, 
                    "error": "Content still exceeds limit but could not be automatically summarized. Try manual editing instead.",
                    "exceeds_limit": exceeds_limit,
                    "total_char_count": total_char_count,
                    "char_limit": char_limit
                }), 400
            else:
                # Content doesn't need summarization
                logger.info("Content doesn't need summarization")
                return jsonify({
                    "success": True,
                    "files": extracted_files_data,
                    "combined_preview": combined_preview_content,
                    "total_char_count": total_char_count,
                    "char_limit": char_limit,
                    "exceeds_limit": exceeds_limit,
                    "warning": "No summarization needed. Content is already within character limit.",
                    "was_summarized": False
                })

        logger.info(f"Returning preview content - total_char_count: {total_char_count}, was_summarized: {was_summarized}")
        return jsonify({
            "success": True,
            "files": extracted_files_data,
            "combined_preview": combined_preview_content,
            "total_char_count": total_char_count,
            "char_limit": char_limit,
            "exceeds_limit": exceeds_limit,
            "warning": warning_message,
            "was_summarized": was_summarized,
            "summarization_stats": summarization_result
        })
    except Exception as e:
        logger.error(f"Error in admin_preview_upload: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

def gpt_summarize_text(text, target_length=None, max_length=50000):
    """Summarize text using GPT-4.
    Returns the summarized text.
    """
    current_length = len(text)
    cleaned_text = text.strip()
    
    if not cleaned_text:
        return "", 0
        
    if current_length <= (target_length or max_length):
        return cleaned_text, 0
    
    # Use a fixed target length close to the maximum to ensure minimal content loss
    if current_length > 50000:
        target_length = 50000  # Maximum target for very large documents
    elif current_length > target_length:
        # For documents that need reduction, set target to at least 80% of current length
        target_length = max(target_length, int(current_length * 0.8))
    
    # Calculate a conservative reduction factor to preserve more content
    reduction_factor = max(0.1, min(0.3, 1 - (target_length / current_length)))
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """You are a text summarization assistant. Your task is to:
1. Preserve ALL important facts, key concepts, definitions, and essential information
2. Maintain the original document's structure, sections, and flow
3. Keep ALL section titles, headers, and subheaders exactly as they appear
4. Remove only clear redundancies and verbose explanations
5. Do not add any commentary or content not in the original"""},
                {"role": "user", "content": f"Please summarize the following text to approximately {target_length} characters while preserving as much original content as possible:\n\n{cleaned_text}"}
            ],
            max_tokens=4000
        )
        
        summary = response['choices'][0]['message']['content'].strip()
        percent_reduced = round(((current_length - len(summary)) / current_length) * 100, 1)
        
        return summary, percent_reduced
        
    except Exception as e:
        logger.error(f"Error in GPT summarization: {e}")
        return smart_text_summarization(text, target_length, max_length), 0

@app.route('/admin/upload', methods=['POST'])
@requires_auth
def admin_upload():
    """Handles the creation of a new chatbot."""
    db = get_db()
    try:
        logger.info("=== ADMIN_UPLOAD START ===")
        logger.info(f"Request method: {request.method}")
        logger.info(f"Request content type: {request.content_type}")
        logger.info(f"Request form keys: {list(request.form.keys())}")
        logger.info(f"Request files keys: {list(request.files.keys())}")
        
        chatbot_code = request.form.get('course_name')
        display_name = request.form.get('display_name')
        description = request.form.get('description', '')
        category = request.form.get('category', 'standard')
        intro_message = request.form.get('intro_message', 'Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day.')
        default_quota = int(request.form.get('default_quota', 3))
        char_limit = int(request.form.get('char_limit', 50000))
        auto_summarize = request.form.get('auto_summarize', 'true').lower() == 'true'
        
        # 👈 NEW: Handle auto-delete setting safely
        auto_delete_days = request.form.get('auto_delete_days')
        if auto_delete_days and auto_delete_days.strip():
            try:
                auto_delete_days = int(auto_delete_days)
                logger.info(f"Auto-delete setting: {auto_delete_days} days")
            except ValueError:
                logger.warning(f"Invalid auto_delete_days value: {auto_delete_days}, using None")
                auto_delete_days = None
        else:
            auto_delete_days = None
            logger.info("Auto-delete setting: disabled (conversations will be kept indefinitely)")
        
        final_content = ""
        content_source = "unknown"
        
        # Log what we received for debugging
        logger.info(f"Admin upload - chatbot_code: {chatbot_code}, display_name: {display_name}")
        logger.info(f"Admin upload - char_limit: {char_limit}, auto_summarize: {auto_summarize}, category: {category}")
        
        if not chatbot_code or not display_name:
            error_msg = "Chatbot ID (course_name) and Display Name are required."
            logger.error(f"Validation error: {error_msg}")
            return jsonify({"success": False, "error": error_msg}), 400
        
        # Check if chatbot code already exists
        existing_chatbot = ChatbotContent.get_by_code(db, chatbot_code.upper())
        if existing_chatbot:
            return jsonify({"success": False, "error": f"Chatbot with ID '{chatbot_code}' already exists. Please use a unique ID."}), 400

        # CONTENT SOURCE DETERMINATION - HIGHEST PRIORITY TO combined_content
        # 1. First priority: Use combined_content if it exists and has content
        if 'combined_content' in request.form and request.form.get('combined_content', '').strip():
            combined_content = request.form.get('combined_content')
            logger.info(f"Using combined_content as primary source (length: {len(combined_content)})")
            final_content = combined_content
            content_source = "combined_content"
        
        # 2. Second priority: Use files only if combined_content is not available
        elif 'files' in request.files:
            files = request.files.getlist('files')
            if not files or all(not f.filename for f in files):
                return jsonify({"success": False, "error": "No files uploaded."}), 400
            
            logger.info(f"Processing {len(files)} files for content extraction")
            content_parts = []
            failed_files = []
            
            for file_storage in files:
                if file_storage and file_storage.filename:
                    try:
                        logger.info(f"Extracting text from {file_storage.filename}")
                        text = extract_text_from_file(file_storage)
                        if text.strip():
                            content_parts.append(text)
                            logger.info(f"Successfully extracted {len(text)} characters from {file_storage.filename}")
                        else:
                            logger.warning(f"No content extracted from {file_storage.filename}")
                            failed_files.append(file_storage.filename)
                    except Exception as e:
                        logger.error(f"Error processing {file_storage.filename}: {str(e)}")
                        failed_files.append(file_storage.filename)
            
            if not content_parts:
                return jsonify({
                    "success": False, 
                    "error": "No content could be extracted from any of the uploaded files.",
                    "failed_files": failed_files
                }), 400
                
            final_content = "\n\n".join(content_parts)
            logger.info(f"Extracted content from files, total length: {len(final_content)}")
            content_source = "files"
            
            if failed_files:
                logger.warning(f"Some files failed to process: {failed_files}")
        
        
        # 3. No valid content source found
        else:
            logger.error("No valid content source found (neither combined_content nor files)")
            return jsonify({"success": False, "error": "No content provided. Either upload files or ensure preview content is submitted."}), 400

        # Validate final content
        if not final_content.strip():
            logger.error(f"Final content is empty after processing from source: {content_source}")
            return jsonify({"success": False, "error": "Extracted or provided content is empty. Please check your files or edited content."}), 400

        # Normalize newline characters before length check
        final_content = final_content.replace('\r\n', '\n')
        logger.info(f"Normalized final_content length: {len(final_content)} chars")

        # LENGTH CHECK & AUTO-SUMMARIZATION
        # If content exceeds limit and auto-summarize is enabled, try to summarize
        if len(final_content) > char_limit:
            logger.info(f"Content length {len(final_content)} exceeds limit {char_limit}")
            if auto_summarize:
                logger.info(f"Applying automatic summarization")
                original_length = len(final_content)
                
                # Show API usage cost warning to the admin
                api_usage_warning = ""
                estimated_tokens = original_length / 4  # Rough estimate: 4 chars per token
                estimated_cost = (estimated_tokens / 1_000_000) * 0.15  # $0.15 per 1M input tokens
                output_tokens = original_length / 4  # Rough estimate: 4 chars per token
                output_cost = (output_tokens / 1_000_000) * 0.60  # $0.60 per 1M output tokens
                estimated_cost = estimated_cost + output_cost
                if original_length > 10000:  # Only show warning for larger content
                    api_usage_warning = f"Note: Using GPT-4o-mini for summarization will cost approximately ${estimated_cost:.2f} for this content."
                    logger.info(f"API cost: ${estimated_cost:.2f} for {estimated_tokens:.0f} input tokens, {output_tokens:.0f} output tokens")
                
                # Apply GPT summarization with fallback to rule-based summarization
                final_content, percent_reduced = gpt_summarize_text(final_content, target_length=int(char_limit * 0.95), max_length=char_limit)
                
                summarized_length = len(final_content)
                logger.info(f"Content reduced from {original_length} to {summarized_length} characters ({percent_reduced}% reduction)")
                
                # Check if still over limit after summarization
                if summarized_length > char_limit:
                    logger.warning(f"Content still exceeds limit after summarization: {summarized_length} > {char_limit}")
                    return jsonify({
                        "success": False, 
                        "error": "Content too long",
                        "warning": f"Content length ({summarized_length:,} characters) still exceeds the limit ({char_limit:,}) after automatic summarization. Please edit manually.",
                        "content_length": summarized_length,
                        "char_limit": char_limit
                    }), 400
            else:
                logger.info(f"Auto-summarize disabled, returning error")
                return jsonify({
                    "success": False, 
                    "error": "Content too long",
                    "warning": f"Content length ({len(final_content):,} characters) exceeds the specified limit ({char_limit:,} characters). Please enable auto-summarize or reduce content manually.",
                    "content_length": len(final_content),
                    "char_limit": char_limit,
                    "auto_summarize_enabled": auto_summarize
                }), 400

        # Create new chatbot (or update if editing)
        logger.info(f"Creating chatbot with final content length: {len(final_content)}")
        logger.info(f"Content source was: {content_source}")
        
        # Get guidelines from form
        system_prompt_guidelines = request.form.get('system_prompt_guidelines')
        if not system_prompt_guidelines:
            # Provide default guidelines if not provided
            system_prompt_guidelines = generate_default_guidelines()
            logger.info("Using default system prompt guidelines as none were provided")
        
        # Generate role that maintains connection with content
        system_prompt_role = "You are an AI assistant specialized in understanding and explaining the provided content. Your role is to provide accurate, helpful, and relevant information while maintaining a professional tone."
        
        # Handle content summarization if needed
        if len(final_content) > char_limit and auto_summarize:
            final_content, percent_reduced = gpt_summarize_text(final_content, char_limit)
            if percent_reduced > 0:
                system_prompt_role = f"""You are an AI assistant specialized in understanding and explaining the provided content. This content is a summarized version of a larger document that has been reduced by {percent_reduced}% while preserving key information."""
            
        new_chatbot = ChatbotContent.create_or_update(
            db=db,
            code=chatbot_code.upper(),
            name=display_name,
            content=final_content,
            description=description,
            quota=default_quota,
            intro_message=intro_message,
            char_limit=char_limit,
            is_active=True,
            category=category,
            system_prompt_role=system_prompt_role,
            system_prompt_guidelines=system_prompt_guidelines,
            auto_delete_days=auto_delete_days  # 👈 NEW: Auto-delete setting
        )
        db.flush()  # Ensure we get the chatbot ID
        
        # Handle LO Root IDs for access control
        lo_root_ids_str = request.form.get('lo_root_ids', '').strip()
        if lo_root_ids_str:
            lo_root_ids = [lo_id.strip() for lo_id in lo_root_ids_str.split(';') if lo_id.strip()]
            logger.info(f"Adding {len(lo_root_ids)} LO Root IDs for access control: {lo_root_ids}")
            
            for lo_root_id in lo_root_ids:
                if lo_root_id:  # Ensure it's not empty
                    association = ChatbotLORootAssociation(
                        chatbot_id=new_chatbot.id,
                        lo_root_id=lo_root_id
                    )
                    db.add(association)
        else:
            logger.info("No LO Root IDs specified - chatbot will be accessible to all users")
        
        db.commit()
        
        # Reload program content in memory to include the new chatbot
        load_program_content() 
        
        logger.info(f"Successfully created chatbot: {chatbot_code.upper()} - {display_name}")
        return jsonify({"success": True, "message": "Chatbot created successfully!"})

    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in admin_upload: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        if db: close_db(db)

def generate_content_aware_role(content, char_limit=None):
    """Generate a role-based system prompt that maintains connection with the content.
    If char_limit is provided, this is for a summarized version of the content."""
    if char_limit and len(content) > char_limit:
        return f"""You are an AI assistant specialized in understanding and explaining the provided content. This content is a summarized version of a larger document, focusing on key information while maintaining the original context and meaning.

CONTENT CONTEXT:
Original Length: {len(content)} characters
Target Length: {char_limit} characters
Content Type: Summarized Document

Your role is to provide accurate, helpful, and relevant information while maintaining awareness that this is a summary of a more detailed document."""
    else:
        return """You are an AI assistant specialized in understanding and explaining the provided content. Your role is to provide accurate, helpful, and relevant information while maintaining a professional tone and basing all responses solely on the provided content."""

def generate_default_guidelines():
    return """
    <h2>Chatbot Guidelines</h2>
    <ul>
        <li>Please be respectful in your conversation</li>
        <li>Keep questions relevant to the program</li>
        <li>For technical issues, contact your administrator</li>
    </ul>
    """

def get_intro_message(program_code):
    """Get intro message for a program from the database and format placeholders"""
    db = get_db()
    try:
        chatbot = ChatbotContent.get_by_code(db, program_code)
        if not chatbot:
            close_db(db)
            return None
            
        # Format the intro message with actual program name and quota
        formatted_message = chatbot.intro_message.format(
            program=chatbot.name,
            quota=chatbot.quota
        )
        close_db(db)
        return formatted_message
    except Exception as e:
        close_db(db)
        logger.error(f"Error getting intro message for {program_code}: {e}")
        return None

@app.route('/admin/delete_chatbot', methods=['POST'])
@requires_auth
def admin_delete_chatbot():
    """Delete a chatbot by setting its is_active flag to False."""
    try:
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = request.form.get('chatbot_code') or request.form.get('chatbot_name')
        if not chatbot_code:
            return jsonify({"success": False, "error": "Chatbot code is required"}), 400

        db = get_db()
        try:
            chatbot = ChatbotContent.get_by_code(db, chatbot_code)
            if not chatbot:
                return jsonify({"success": False, "error": "Chatbot not found"}), 404

            # Set is_active to False instead of actually deleting
            chatbot.is_active = False
            db.commit()

            # Reload program content in memory
            load_program_content()

            return jsonify({
                "success": True,
                "message": f"Chatbot {chatbot_code} has been deactivated successfully"
            })

        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting chatbot: {str(e)}")
            return jsonify({"success": False, "error": str(e)}), 500
        finally:
            close_db(db)

    except Exception as e:
        logger.error(f"Error in admin_delete_chatbot: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/admin/update_description', methods=['POST'])
@requires_auth
def admin_update_description():
    """Update the description of an existing chatbot."""
    db = get_db()
    try:
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = request.form.get('chatbot_code') or request.form.get('chatbot_name')
        new_description = request.form.get('description')

        if not chatbot_code or new_description is None: # Description can be an empty string
            return jsonify({"success": False, "error": "Chatbot code and description are required."}), 400

        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found."}), 404

        chatbot.description = new_description
        db.commit()
        load_program_content() # Reload content to reflect changes

        logger.info(f"Successfully updated description for chatbot: {chatbot_code}")
        return jsonify({"success": True, "message": "Description updated successfully!"})

    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in admin_update_description: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        if db: close_db(db)

@app.route('/admin/restore_chatbot', methods=['POST'])
@requires_auth
def admin_restore_chatbot():
    """Restore a chatbot by setting its is_active flag to True."""
    db = get_db()
    try:
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = request.form.get('chatbot_code') or request.form.get('chatbot_name')
        if not chatbot_code:
            return jsonify({"success": False, "error": "Chatbot code is required"}), 400

        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found."}), 404

        chatbot.is_active = True
        db.commit()
        load_program_content()  # Reload content to reflect changes

        logger.info(f"Successfully restored chatbot: {chatbot_code}")
        return jsonify({"success": True, "message": "Chatbot restored successfully!"})

    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in admin_restore_chatbot: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        if db: close_db(db)

@app.route('/admin/permanent_delete_chatbot', methods=['POST'])
@requires_auth
def admin_permanent_delete_chatbot():
    """Permanently delete a chatbot from the database."""
    db = get_db()
    try:
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = request.form.get('chatbot_code') or request.form.get('chatbot_name')
        if not chatbot_code:
            return jsonify({"success": False, "error": "Chatbot code is required"}), 400

        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found."}), 404

        chatbot_id = chatbot.id
        chatbot_name = chatbot.name

        # Delete related data first to avoid foreign key constraints
        logger.info(f"Starting permanent deletion process for chatbot: {chatbot_code} (ID: {chatbot_id})")
        
        # 1. Delete chat history for this chatbot
        chat_history_count = db.query(ChatHistory).filter(ChatHistory.program_code == chatbot_code).count()
        if chat_history_count > 0:
            db.query(ChatHistory).filter(ChatHistory.program_code == chatbot_code).delete()
            logger.info(f"Deleted {chat_history_count} chat history records for chatbot {chatbot_code}")
        
        # 2. Delete LO Root ID associations
        lo_associations_count = db.query(ChatbotLORootAssociation).filter(ChatbotLORootAssociation.chatbot_id == chatbot_id).count()
        if lo_associations_count > 0:
            db.query(ChatbotLORootAssociation).filter(ChatbotLORootAssociation.chatbot_id == chatbot_id).delete()
            logger.info(f"Deleted {lo_associations_count} LO Root ID associations for chatbot {chatbot_code}")
        
        # 3. Finally, delete the chatbot itself
        db.delete(chatbot)
        db.commit()
        
        # Also update the in-memory program content
        load_program_content()

        logger.info(f"Successfully permanently deleted chatbot: {chatbot_code} ({chatbot_name})")
        return jsonify({
            "success": True, 
            "message": f"Chatbot '{chatbot_name}' and all associated data have been permanently deleted!"
        })

    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in admin_permanent_delete_chatbot: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        if db: close_db(db)

@app.route('/update_intro_message', methods=['POST'])
@requires_auth
def update_intro_message():
    """Update the intro message of a chatbot."""
    db = get_db()
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
            
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = data.get('chatbot_code') or data.get('chatbot_name')
        intro_message = data.get('intro_message')
        
        if not chatbot_code or intro_message is None:
            return jsonify({"success": False, "error": "Chatbot code and intro message are required"}), 400
            
        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found"}), 404
            
        chatbot.intro_message = intro_message
        db.commit()
        
        # Reload content to reflect changes
        load_program_content()
        
        logger.info(f"Successfully updated intro message for chatbot: {chatbot_code}")
        return jsonify({"success": True, "message": "Intro message updated successfully"})
        
    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in update_intro_message: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if db: close_db(db)

@app.route('/update_quota', methods=['POST'])
@requires_auth
def update_quota():
    """Update the daily question quota of a chatbot."""
    db = get_db()
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
            
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = data.get('chatbot_code') or data.get('chatbot_name')
        quota = data.get('quota')
        
        if not chatbot_code or quota is None:
            return jsonify({"success": False, "error": "Chatbot code and quota are required"}), 400
            
        # Validate quota
        try:
            quota = int(quota)
            if quota < 1 or quota > 100:
                return jsonify({"success": False, "error": "Quota must be between 1 and 100"}), 400
        except ValueError:
            return jsonify({"success": False, "error": "Quota must be a valid number"}), 400
            
        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found"}), 404
            
        chatbot.quota = quota
        db.commit()
        
        # Reload content to reflect changes
        load_program_content()
        
        logger.info(f"Successfully updated quota for chatbot: {chatbot_code}")
        return jsonify({"success": True, "message": "Quota updated successfully"})
        
    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in update_quota: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if db: close_db(db)

@app.route('/get_chatbot_content', methods=['POST'])
@requires_auth
def get_chatbot_content():
    """Get the content of a chatbot for editing."""
    db = get_db()
    try:
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = request.form.get('chatbot_code') or request.form.get('chatbot_name')
        if not chatbot_code:
            return jsonify({"success": False, "error": "Chatbot code is required"}), 400
            
        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found"}), 404
            
        return jsonify({
            "success": True,
            "content": chatbot.content,
            "char_count": len(chatbot.content)
        })
        
    except Exception as e:
        logger.error(f"Error in get_chatbot_content: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if db: close_db(db)

@app.route('/admin/get_chatbot_content/<chatbot_code>', methods=['GET'])
@requires_auth
def admin_get_chatbot_content(chatbot_code):
    """Get the content of a chatbot for editing (admin route)."""
    db = get_db()
    try:
        # No need to check query params as we get the code from URL path
        if not chatbot_code:
            return jsonify({"success": False, "error": "Chatbot code is required"}), 400
            
        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found"}), 404
            
        return jsonify({
            "success": True,
            "content": chatbot.content,
            "char_count": len(chatbot.content),
            "char_limit": chatbot.char_limit,
            "system_prompt_role": chatbot.system_prompt_role,
            "system_prompt_guidelines": chatbot.system_prompt_guidelines
        })
        
    except Exception as e:
        logger.error(f"Error in admin_get_chatbot_content: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if db: close_db(db)

@app.route('/update_chatbot_content', methods=['POST'])
@requires_auth
def update_chatbot_content():
    """Update the content of an existing chatbot."""
    db = get_db()
    try:
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = request.form.get('chatbot_code') or request.form.get('chatbot_name')
        content = request.form.get('content')
        
        if not chatbot_code or content is None:
            return jsonify({"success": False, "error": "Chatbot code and content are required"}), 400
            
        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found"}), 404
            
        # Check if content exceeds character limit
        char_limit = chatbot.char_limit or 50000
        if len(content) > char_limit:
            return jsonify({
                "success": False,
                "error": f"Content exceeds character limit of {char_limit}",
                "char_count": len(content),
                "char_limit": char_limit
            }), 400
            
        chatbot.content = content
        db.commit()
        
        # Update in-memory content and hash
        load_program_content()
        
        logger.info(f"Successfully updated content for chatbot: {chatbot_code}")
        return jsonify({"success": True, "message": "Chatbot content updated successfully"})
        
    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in update_chatbot_content: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if db: close_db(db)

@app.route('/admin/update_chatbot_content', methods=['POST'])
@requires_auth
def admin_update_chatbot_content():
    """Update the content of an existing chatbot through admin interface."""
    db = get_db()
    try:
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = request.form.get('chatbot_code') or request.form.get('chatbot_name')
        content = request.form.get('content')
        auto_summarize = request.form.get('auto_summarize', 'true').lower() == 'true'
        system_prompt_guidelines = request.form.get('system_prompt_guidelines')
        
        if not chatbot_code or content is None:
            return jsonify({"success": False, "error": "Chatbot code and content are required"}), 400
            
        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found"}), 404
            
        # Check if content exceeds character limit
        char_limit = int(request.form.get('char_limit', chatbot.char_limit or 50000))
        
        # If content exceeds limit and auto-summarize is enabled, try to summarize
        if len(content) > char_limit:
            if auto_summarize:
                logger.info(f"Content exceeded limit ({len(content)} > {char_limit}). Applying automatic summarization.")
                original_length = len(content)
                
                # Show API usage cost warning to the admin
                api_usage_warning = ""
                estimated_tokens = original_length / 4  # Rough estimate: 4 chars per token
                estimated_cost = (estimated_tokens / 1_000_000) * 0.15  # $0.15 per 1M input tokens
                output_tokens = original_length / 4  # Rough estimate: 4 chars per token
                output_cost = (output_tokens / 1_000_000) * 0.60  # $0.60 per 1M output tokens
                estimated_cost = estimated_cost + output_cost
                if original_length > 10000:  # Only show warning for larger content
                    api_usage_warning = f"Note: Using GPT-4o-mini for summarization will cost approximately ${estimated_cost:.2f} for this content."
                    logger.info(f"API cost: ${estimated_cost:.2f} for {estimated_tokens:.0f} input tokens, {output_tokens:.0f} output tokens")
                
                # Apply GPT summarization with fallback to rule-based summarization
                content, percent_reduced = gpt_summarize_text(content, target_length=int(char_limit * 0.95), max_length=char_limit)
                
                # Calculate reduction stats
                summarization_stats = {
                    "original_length": original_length,
                    "final_length": len(content),
                    "chars_removed": original_length - len(content),
                    "percent_reduced": percent_reduced
                }
                
                logger.info(f"Content reduced from {original_length} to {len(content)} characters through automatic summarization.")
                return jsonify({
                    "success": True, 
                    "message": "Chatbot content updated successfully with summarization",
                    "was_summarized": True,
                    "warning": f"Content was automatically summarized to fit within the character limit of {char_limit:,} characters. {api_usage_warning}",
                    "summarization_stats": summarization_stats,
                    "content_length": len(content),
                    "char_limit": char_limit
                })
            else:
                return jsonify({
                    "success": False, 
                    "error": "Content too long",
                    "warning": f"Content exceeds character limit of {char_limit:,} characters (current: {len(content):,} characters). Enable auto-summarize to reduce automatically.",
                    "content_length": len(content),
                    "char_limit": char_limit
                }), 400
        
        # Only update the character limit if it's different
        if chatbot.char_limit != char_limit:
            chatbot.char_limit = char_limit
            
        # Update content and system prompts
        chatbot.content = content
        if system_prompt_guidelines is not None:
            chatbot.system_prompt_guidelines = system_prompt_guidelines
            
        db.commit()
        
        # Clear the cache for get_cached_response as prompts might have changed
        get_cached_response.cache_clear()
        logger.info("Cleared get_cached_response cache due to chatbot content/prompt update.")

        # Update in-memory content and hash
        load_program_content()
        
        logger.info(f"Successfully updated content and system prompts for chatbot: {chatbot_code}")
        return jsonify({"success": True, "message": "Chatbot content and system prompts updated successfully"})
        
    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in admin_update_chatbot_content: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if db: close_db(db)

@app.route('/admin/update_category', methods=['POST'])
@requires_auth
def admin_update_category():
    """Update the category of an existing chatbot."""
    db = get_db()
    try:
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = request.form.get('chatbot_code') or request.form.get('chatbot_name')
        new_category = request.form.get('category')

        if not chatbot_code or not new_category:
            return jsonify({"success": False, "error": "Chatbot code and category are required."}), 400

        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found."}), 404

        # Validate category
        valid_categories = ['standard', 'tap', 'jsa', 'elearning']
        if new_category not in valid_categories:
            return jsonify({"success": False, "error": f"Invalid category. Must be one of: {', '.join(valid_categories)}"}), 400

        chatbot.category = new_category
        db.commit()
        load_program_content() # Reload content to reflect changes

        logger.info(f"Successfully updated category to '{new_category}' for chatbot: {chatbot_code}")
        return jsonify({"success": True, "message": "Category updated successfully!"})

    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in admin_update_category: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        if db: close_db(db)

@app.route('/admin/update_lo_root_ids', methods=['POST'])
@requires_auth
def admin_update_lo_root_ids():
    """Update the LO Root IDs for an existing chatbot."""
    db = get_db()
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
            
        chatbot_code = data.get('chatbot_code')
        lo_root_ids_str = data.get('lo_root_ids', '').strip()
        
        if not chatbot_code:
            return jsonify({"success": False, "error": "Chatbot code is required"}), 400
            
        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found"}), 404
        
        # Parse LO Root IDs from semicolon-separated string
        lo_root_ids = []
        if lo_root_ids_str:
            lo_root_ids = [lo_id.strip() for lo_id in lo_root_ids_str.split(';') if lo_id.strip()]
        
        # Remove existing LO Root ID associations
        db.query(ChatbotLORootAssociation).filter(
            ChatbotLORootAssociation.chatbot_id == chatbot.id
        ).delete()
        
        # Add new LO Root ID associations
        for lo_root_id in lo_root_ids:
            if lo_root_id:  # Ensure it's not empty
                association = ChatbotLORootAssociation(
                    chatbot_id=chatbot.id,
                    lo_root_id=lo_root_id
                )
                db.add(association)
        
        db.commit()
        
        # Reload content to reflect changes
        load_program_content()
        
        logger.info(f"Successfully updated LO Root IDs for chatbot {chatbot_code}: {lo_root_ids}")
        
        # Provide helpful feedback message
        if lo_root_ids:
            message = f"Access control updated! Only users with LO Root IDs [{', '.join(lo_root_ids)}] can access this chatbot."
        else:
            message = "Access control removed! All users can now access this chatbot."
            
        return jsonify({"success": True, "message": message})
        
    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in admin_update_lo_root_ids: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if db: close_db(db)

# Custom cosine similarity function to avoid scikit-learn dependency issues
def custom_cosine_similarity(a, b):
    """Calculate cosine similarity between two vectors"""
    # Convert inputs to numpy arrays if they aren't already
    a = np.array(a, dtype=np.float64)
    b = np.array(b, dtype=np.float64)
    
    # Ensure vectors are flattened
    a = a.flatten()
    b = b.flatten()
    
    # Calculate dot product
    dot_product = np.dot(a, b)
    
    # Calculate magnitudes
    magnitude_a = np.sqrt(np.sum(np.square(a)))
    magnitude_b = np.sqrt(np.sum(np.square(b)))
    
    # Calculate cosine similarity
    if magnitude_a == 0 or magnitude_b == 0:
        return 0  # Avoid division by zero
    else:
        return dot_product / (magnitude_a * magnitude_b)

# Helper function to automatically summarize text
def smart_text_summarization(text, target_length=None, max_length=50000):
    """
    Intelligently summarize text to meet a target length using various techniques.
    
    Args:
        text (str): The input text to summarize
        target_length (int, optional): Target character length. If None, defaults to 80% of max_length
        max_length (int): Maximum allowed length
        
    Returns:
        str: Summarized text within the target length
    """
    if not text:
        return ""
    
    # If text is already shorter than max_length, return as is
    if len(text) <= max_length:
        return text
    
    if target_length is None:
        target_length = int(max_length * 0.8)  # Target 80% of max to leave buffer
    
    original_length = len(text)
    logger.info(f"Starting summarization: {original_length} characters to target {target_length} characters")
    
    # Step 1: Apply basic cleanup
    # Remove duplicate newlines and spaces
    cleaned_text = re.sub(r'\n{3,}', '\n\n', text)
    cleaned_text = re.sub(r' {2,}', ' ', cleaned_text)
    
    current_length = len(cleaned_text)
    logger.info(f"After basic cleanup: {current_length} characters ({original_length - current_length} removed)")
    
    if current_length <= target_length:
        return cleaned_text
    
    # Step 2: Remove common boilerplate content
    if current_length > target_length:
        # Remove common headers, footers, etc.
        patterns_to_remove = [
            r'(?i)confidential.*?notice.*?\n\n',            # Confidentiality notices
            r'(?i)copyright.*?reserved.*?\n\n',             # Copyright notices
            r'(?i)table of contents.*?\n\n',                # Table of contents markers
            r'(?i)page \d+ of \d+',                         # Page numbers format 1
            r'(?i)page\s+\d+',                              # Page numbers format 2 
            r'(?i)slide\s+\d+',                             # Slide numbers
            r'(?i)this document contains.*?\n\n',           # Document notices
            r'(?i)(http|https)://\S+',                      # URLs
            r'(?i)www\.\S+',                                # Web addresses
            r'(?i)email:.*?\n',                             # Email addresses
            r'(?i)tel:.*?\n',                               # Phone numbers
            r'(?i)all rights reserved.*?\n\n',              # Rights statements
            r'(?i)terms and conditions.*?\n\n',             # Terms sections
            r'(?i)for more information.*?\n\n',             # Common footer text
            r'(?i)disclaimer.*?\n\n',                       # Disclaimer sections
            r'(?i)facilitators?\s+say:',                    # Facilitator instructions
            r'(?i)facilitators?\s+notes?:',                 # Facilitator notes
            r'(?i)notes?\s+to\s+facilitators?:',            # Notes to facilitator
            r'(?i)course\s+materials?:',                    # Course materials heading
            r'(?i)recommended\s+equipment:',                # Equipment list heading
            r'(?i)session\s+outline:',                      # Session outline heading
            r'(?i)^\s*\d+\.\d+\.\d+\s+',                   # Detailed numbering schemes
            r'(?i)header\s*\d*\s*:',                        # Header indicators
            r'(?i)footer\s*\d*\s*:',                        # Footer indicators
            r'(?i)\[\s*end\s+of\s+\w+\s*\]',                # End markers
            r'(?im)^\s*[\d\.]+\s+agenda\s*$',               # Agenda numbered headers
            r'(?im)^\s*[\d\.]+\s+purpose\s*$',              # Purpose numbered headers
            r'(?im)^\s*[\d\.]+\s+overview\s*$',             # Overview numbered headers
        ]
        
        for pattern in patterns_to_remove:
            cleaned_text = re.sub(pattern, '', cleaned_text)
        
        current_length = len(cleaned_text)
        logger.info(f"After boilerplate removal: {current_length} characters ({original_length - current_length} removed)")
        
        if current_length <= target_length:
            return cleaned_text
    
    # Step 3: Remove duplicate paragraphs
    if current_length > target_length:
        paragraphs = cleaned_text.split('\n\n')
        unique_paragraphs = []
        content_hashes = set()
        
        for para in paragraphs:
            # Skip very short paragraphs that are likely just numbers or formatting
            if len(para.strip()) < 5:
                continue
                
            # Create a simple hash of paragraph content
            # Normalize for better duplicate detection
            normalized_para = re.sub(r'[\d\s,\.\(\)]', '', para.lower().strip())
            if len(normalized_para) < 10:  # If normalized content is too small, it's likely not meaningful
                unique_paragraphs.append(para)
                continue
                
            para_hash = hashlib.md5(normalized_para.encode()).hexdigest()
            if para_hash not in content_hashes:
                content_hashes.add(para_hash)
                unique_paragraphs.append(para)
        
        cleaned_text = '\n\n'.join(unique_paragraphs)
        current_length = len(cleaned_text)
        logger.info(f"After duplicate removal: {current_length} characters ({original_length - current_length} removed)")
        
        if current_length <= target_length:
            return cleaned_text
    
    # Step 4: Identify and trim less important sections
    if current_length > target_length:
        # Look for appendices, references, notes sections and trim them
        sections_to_trim = [
            (r'(?i)appendix.*?$', r'(?i)\n+[^\n]*?appendix.*?\n'),
            (r'(?i)references.*?$', r'(?i)\n+[^\n]*?references.*?\n'),
            (r'(?i)bibliography.*?$', r'(?i)\n+[^\n]*?bibliography.*?\n'),
            (r'(?i)notes.*?$', r'(?i)\n+[^\n]*?notes.*?\n'),
            (r'(?i)footnotes.*?$', r'(?i)\n+[^\n]*?footnotes.*?\n'),
            (r'(?i)attachment.*?$', r'(?i)\n+[^\n]*?attachment.*?\n'),
            (r'(?i)exhibit.*?$', r'(?i)\n+[^\n]*?exhibit.*?\n'),
        ]
        
        for section_pattern, section_start in sections_to_trim:
            if current_length > target_length:
                match = re.search(section_start, cleaned_text)
                if match:
                    end_pos = match.start()
                    remaining_text = cleaned_text[:end_pos].strip()
                    appendix_notice = "\n\n[Content truncated: supplementary sections removed]"
                    cleaned_text = remaining_text + appendix_notice
                    current_length = len(cleaned_text)
                    logger.info(f"After trimming section: {current_length} characters ({original_length - current_length} removed)")
                    
                    if current_length <= target_length:
                        return cleaned_text
                        
    # Step 5: Remove repetitive phrases and instructions
    if current_length > target_length:
        # Define patterns for repetitive or instructional content
        repetitive_patterns = [
            (r'(?i)activity\s+\d+\s*:\s*[^\n]+\n', '[Activity description removed]\n'),
            (r'(?i)exercise\s+\d+\s*:\s*[^\n]+\n', '[Exercise description removed]\n'),
            (r'(?i)task\s+\d+\s*:\s*[^\n]+\n', '[Task description removed]\n'),
            (r'(?i)step\s+\d+\s*:\s*[^\n]+\n', '[Step description removed]\n'),
            (r'(?i)instructions?\s*:\s*[^\n]+\n', '[Instructions removed]\n'),
            (r'(?i)guidelines?\s*:\s*[^\n]+\n', '[Guidelines removed]\n'),
            (r'(?i)note\s+to\s+learners?\s*:\s*[^\n]+\n', ''),
            (r'(?i)\[\s*begin\s+activity\s*\][^\[]*\[\s*end\s+activity\s*\]', '[Activity content removed]'),
            (r'(?i)objectives?\s*:\s*\n(?:\s*[-•]\s*[^\n]+\n)+', '[Objectives section removed]\n'),
            (r'(?i)materials?\s+needed\s*:\s*\n(?:\s*[-•]\s*[^\n]+\n)+', '[Materials list removed]\n'),
            (r'(?i)key\s+points\s*:\s*\n(?:\s*[-•]\s*[^\n]+\n)+', '[Key points section removed]\n'),
        ]
        
        for pattern, replacement in repetitive_patterns:
            cleaned_text = re.sub(pattern, replacement, cleaned_text)
            
        current_length = len(cleaned_text)
        logger.info(f"After removing repetitive content: {current_length} characters ({original_length - current_length} removed)")
            
        if current_length <= target_length:
            return cleaned_text
    
    # Step 6: More aggressive content reduction for very large content 
    if current_length > target_length and current_length > target_length * 1.5:
        # For very large content, preserve document structure but reduce detail
        logger.info(f"Content still too large ({current_length} chars). Applying structural summarization.")
        
        paragraphs = cleaned_text.split('\n\n')
        
        # Keep introduction (first 10% of paragraphs)
        intro_count = max(3, int(len(paragraphs) * 0.1))
        # Keep conclusion (last 10% of paragraphs)
        conclusion_count = max(3, int(len(paragraphs) * 0.1))
        
        # Estimate how many paragraphs we need from the middle
        total_intro_conclusion_length = len('\n\n'.join(paragraphs[:intro_count] + paragraphs[-conclusion_count:]))
        remaining_target = target_length - total_intro_conclusion_length - 100  # 100 chars buffer for section markers
        
        # Select paragraphs evenly distributed from the middle
        if len(paragraphs) > intro_count + conclusion_count and remaining_target > 0:
            # Calculate how many paragraphs we can fit
            middle_paragraphs = paragraphs[intro_count:-conclusion_count] if conclusion_count > 0 else paragraphs[intro_count:]
            
            # First try to keep paragraph headers and key concepts
            key_paragraphs = []
            for para in middle_paragraphs:
                # Check if paragraph is a header (short with title case or caps)
                is_header = len(para.strip()) < 50 and (
                    para.strip().istitle() or 
                    para.strip().isupper() or 
                    re.match(r'^[A-Z][\w\s]+:', para.strip())
                )
                
                # Check for key concept indicators
                has_key_indicators = any(indicator in para.lower() for indicator in [
                    "key point", "important", "critical", "essential", "remember", 
                    "concept", "principle", "main idea", "core", "fundamental"
                ])
                
                if is_header or has_key_indicators:
                    key_paragraphs.append(para)
            
            # Get the total length of key paragraphs
            key_paragraphs_length = sum(len(p) for p in key_paragraphs) + (len(key_paragraphs) * 2)  # +2 for each \n\n
            
            # If we have room for additional paragraphs beyond key ones
            remaining_length = remaining_target - key_paragraphs_length
            if remaining_length > 0 and len(middle_paragraphs) > len(key_paragraphs):
                # Filter out paragraphs we already selected
                remaining_paragraphs = [p for p in middle_paragraphs if p not in key_paragraphs]
                
                # Calculate how many more we can include
                avg_para_length = sum(len(p) for p in remaining_paragraphs) / len(remaining_paragraphs)
                additional_paras_count = int(remaining_length / (avg_para_length + 2))  # +2 for \n\n
                
                # Select additional paragraphs evenly distributed
                if additional_paras_count > 0:
                    step = len(remaining_paragraphs) / additional_paras_count
                    indices = [int(i * step) for i in range(additional_paras_count)]
                    additional_paras = [remaining_paragraphs[i] for i in indices if i < len(remaining_paragraphs)]
                    key_paragraphs.extend(additional_paras)
            
            # Combine all selected paragraphs in proper order
            all_middle_indices = [(middle_paragraphs.index(p), p) for p in key_paragraphs]
            all_middle_indices.sort()  # Sort by original position
            middle_selected = [p for _, p in all_middle_indices]
            
            # Final combination with introduction and conclusion
            final_paragraphs = paragraphs[:intro_count]
            if middle_selected:
                final_paragraphs.append("\n[...content summarized...]\n")
                final_paragraphs.extend(middle_selected)
            final_paragraphs.append("\n[...content summarized...]\n")
            if conclusion_count > 0:
                final_paragraphs.extend(paragraphs[-conclusion_count:])
            
            cleaned_text = '\n\n'.join(final_paragraphs)
            current_length = len(cleaned_text)
            logger.info(f"After structural summarization: {current_length} characters ({original_length - current_length} removed)")
            
            if current_length <= target_length:
                return cleaned_text
    
    # Step 7: If still too long, do proportional reduction
    if current_length > target_length:
        # Calculate how much we need to reduce each paragraph
        paragraphs = cleaned_text.split('\n\n')
        reduction_ratio = target_length / current_length
        
        new_paragraphs = []
        total_length = 0
        
        # Keep introduction (first paragraph) intact
        if paragraphs:
            intro = paragraphs[0]
            new_paragraphs.append(intro)
            total_length += len(intro) + 2  # +2 for the \n\n
        
        # We'll keep paragraphs in proportion to their original size
        for i, para in enumerate(paragraphs[1:-1] if len(paragraphs) > 2 else []):
            # Very short paragraphs are kept intact
            if len(para) < 100:
                new_paragraphs.append(para)
                total_length += len(para) + 2  # +2 for the \n\n
            else:
                # Calculate target length for this paragraph
                para_target_len = max(50, int(len(para) * reduction_ratio * 0.9))  # Use 90% of ratio to leave buffer
                
                # Shorten to complete sentences if possible
                if para_target_len < len(para):
                    # Find the last complete sentence that fits
                    sentences = re.split(r'(?<=[.!?])\s+', para)
                    kept_sentences = []
                    current_len = 0
                    
                    for sentence in sentences:
                        if current_len + len(sentence) + 1 <= para_target_len:  # +1 for space
                            kept_sentences.append(sentence)
                            current_len += len(sentence) + 1
                        else:
                            break
                    
                    if kept_sentences:
                        trimmed_para = ' '.join(kept_sentences)
                        if i % 5 == 0:  # Add indicator every few paragraphs
                            trimmed_para += " [...]"
                    else:
                        # If no complete sentence fits, just truncate with indicator
                        trimmed_para = para[:para_target_len].strip() + " [...]"
                    
                    new_paragraphs.append(trimmed_para)
                    total_length += len(trimmed_para) + 2
            
            # Stop if we've reached the target
            if total_length >= target_length * 0.9:  # Leave 10% for conclusion
                break
        
        # Keep conclusion (last paragraph) intact if possible
        if len(paragraphs) > 1 and total_length + len(paragraphs[-1]) + 2 <= target_length:
            new_paragraphs.append(paragraphs[-1])
            total_length += len(paragraphs[-1]) + 2
        
        if new_paragraphs:
            cleaned_text = '\n\n'.join(new_paragraphs)
            current_length = len(cleaned_text)
            logger.info(f"After proportional reduction: {current_length} characters ({original_length - current_length} removed)")
    
    # Final check - if all else fails, just truncate with notice
    if len(cleaned_text) > max_length:
        truncation_notice = "\n\n[Content truncated to fit within character limit]"
        text_portion = max_length - len(truncation_notice)
        
        # Find last complete sentence before truncation point
        text_to_truncate = cleaned_text[:text_portion]
        last_sentence_end = max(text_to_truncate.rfind('.'), 
                               text_to_truncate.rfind('!'), 
                               text_to_truncate.rfind('?'))
        
        if last_sentence_end > 0 and last_sentence_end > 0.7 * text_portion:
            # If we found a sentence ending and it's reasonably far along
            cleaned_text = cleaned_text[:last_sentence_end+1] + truncation_notice
        else:
            # Otherwise just truncate at character limit
            cleaned_text = cleaned_text[:text_portion] + truncation_notice
        
        current_length = len(cleaned_text)
        logger.info(f"After final truncation: {current_length} characters ({original_length - current_length} removed)")
    
    # Return the cleaned text, which should now be under max_length
    return cleaned_text

@app.route('/admin/upload_user_csv', methods=['POST'])
@requires_auth
def admin_upload_user_csv():
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('admin'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('admin'))

    if not file or not file.filename.endswith('.csv'):
        flash('Invalid file type. Please upload a CSV file.', 'error')
        return redirect(url_for('admin'))

    db = get_db()
    try:
        # Read CSV content into memory
        csv_content = file.read().decode('utf-8-sig')
        df = pd.read_csv(StringIO(csv_content))
        
        # Validate required columns
        required_columns = ['last_name', 'email', 'status', 'lo_root_id']
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            flash(f'Error: Missing required columns: {", ".join(missing_cols)}', 'error')
            return redirect(url_for('admin'))

        # Process users
        new_users_count = 0
        skipped_inactive_count = 0
        skipped_existing_count = 0
        error_messages = []

        for index, row in df.iterrows():
            try:
                # Basic data validation
                last_name = row.get('last_name')
                email = row.get('email')
                status = str(row.get('status', '')).strip().lower()
                lo_root_id_raw = row.get('lo_root_id')

                if not all([last_name, email, status, lo_root_id_raw]):
                    error_messages.append(f"Row {index+2}: Missing one or more required fields.")
                    continue
                
                # Validate email format
                if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    error_messages.append(f"Row {index+2}: Invalid email format for {email}.")
                    continue

                # Filter for "Active" status
                if status != 'active':
                    skipped_inactive_count += 1
                    continue

                # Check if user already exists
                existing_user = db.query(User).filter(User.email == email).first()
                if existing_user:
                    skipped_existing_count += 1
                    continue
                
                # Register new user
                expiry_date_calculated = datetime.utcnow() + timedelta(days=2*365)
                new_user = User(
                    last_name=last_name,
                    email=email,
                    status='Active',
                    date_added=datetime.utcnow(),
                    expiry_date=expiry_date_calculated
                )
                db.add(new_user)
                db.flush()

                # Add lo_root_id(s)
                lo_root_ids_list = [lr_id.strip() for lr_id in str(lo_root_id_raw).split(';') if lr_id.strip()]
                for lr_id in lo_root_ids_list:
                    if lr_id:
                        user_lo_association = UserLORootID(user_id=new_user.id, lo_root_id=lr_id)
                        db.add(user_lo_association)
                
                new_users_count += 1
                
            except Exception as e:
                error_messages.append(f"Row {index+2}: Error processing user - {str(e)}")
                continue

        db.commit()
        flash(f'CSV processed successfully: {new_users_count} new users added. Skipped {skipped_inactive_count} inactive, {skipped_existing_count} existing.', 'success')
        if error_messages:
            for err_msg in error_messages:
                flash(err_msg, 'warning')
                
    except Exception as e:
        if db:
            db.rollback()
        logger.error(f"Error processing CSV data: {str(e)}")
        flash(f'Error processing CSV data: {str(e)}', 'error')
        
    finally:
        if db:
            close_db(db)
        
    return redirect(url_for('admin'))

@app.route('/admin/manage_users')
@requires_auth
def admin_manage_users():
    page = request.args.get('page', 1, type=int)
    per_page = 20 # Users per page
    search_term = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'date_added')
    sort_order = request.args.get('sort_order', 'desc')

    db = get_db()
    try:
        query = db.query(User)

        if search_term:
            search_filter = f"%{search_term}%"
            query = query.filter(
                User.last_name.ilike(search_filter) |
                User.email.ilike(search_filter)
            )
        
        # Sorting logic
        sort_column = getattr(User, sort_by, User.date_added) # Default to date_added
        if sort_order == 'asc':
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        users_pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        users = users_pagination.items

    finally:
        close_db(db)
    
    return render_template('admin/manage_users.html', 
                           users=users, 
                           pagination=users_pagination,
                           search_term=search_term,
                           sort_by=sort_by,
                           sort_order=sort_order)

@app.route('/admin/delete_all_users', methods=['POST'])
@requires_auth
def delete_all_users():
    """Delete all users from the database"""
    db = get_db()
    try:
        User.delete_all_users(db)
        flash('All users have been successfully deleted.', 'success')
    except Exception as e:
        flash(f'Error deleting users: {str(e)}', 'error')
    finally:
        close_db(db)
    return redirect(url_for('admin_manage_users'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@requires_auth
def delete_user(user_id):
    """Delete a specific user from the database"""
    db = get_db()
    try:
        if User.delete_user(db, user_id):
            flash('User has been successfully deleted.', 'success')
        else:
            flash('User not found.', 'error')
    except Exception as e:
        flash(f'Error deleting user: {str(e)}', 'error')
    finally:
        close_db(db)
    return redirect(url_for('admin_manage_users'))

@app.route('/admin/delete_selected_users', methods=['POST'])
@requires_auth
def delete_selected_users():
    """Delete multiple selected users"""
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Invalid request format'})

    user_ids = request.json.get('user_ids', [])
    if not user_ids:
        return jsonify({'success': False, 'error': 'No users selected'})

    db = get_db()
    try:
        success_count = 0
        for user_id in user_ids:
            try:
                user_id = int(user_id)  # Convert string to integer
                if User.delete_user(db, user_id):
                    success_count += 1
            except ValueError:
                continue
        
        if success_count == len(user_ids):
            return jsonify({'success': True, 'message': f'Successfully deleted {success_count} users'})
        else:
            return jsonify({
                'success': True, 
                'message': f'Deleted {success_count} out of {len(user_ids)} users'
            })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        close_db(db)

@app.route('/admin/add_user', methods=['POST'])
@requires_auth
def add_user():
    """Add a new user"""
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Invalid request format'})

    data = request.json
    last_name = data.get('last_name')
    email = data.get('email')
    lo_root_ids = data.get('lo_root_ids', [])

    if not all([last_name, email]):
        return jsonify({'success': False, 'error': 'Missing required fields'})

    db = get_db()
    try:
        # Check if user already exists
        existing_user = User.get_by_credentials(db, last_name, email)
        if existing_user:
            return jsonify({'success': False, 'error': 'User already exists'})

        # Create new user
        expiry_date = datetime.utcnow() + timedelta(days=2*365)
        new_user = User(
            last_name=last_name,
            email=email,
            status='Active',
            date_added=datetime.utcnow(),
            expiry_date=expiry_date,
            visit_count=0
        )
        db.add(new_user)
        db.flush()  # Get the new user's ID

        # Add LO Root IDs
        for lo_root_id in lo_root_ids:
            if lo_root_id:
                user_lo = UserLORootID(user_id=new_user.id, lo_root_id=lo_root_id)
                db.add(user_lo)

        db.commit()
        
        # Send password setup email
        try:
            send_password_setup_email(email, last_name, is_admin_added=True)
            logger.info(f"Password setup email sent to {email} for admin-added user")
        except Exception as e:
            logger.error(f"Failed to send password setup email to {email}: {e}")
            # Don't fail the user creation if email fails
        
        return jsonify({'success': True, 'message': 'User added successfully. Password setup email sent.'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        close_db(db)

@app.route('/admin/get_users')
@requires_auth
def get_users():
    """Get all users as JSON"""
    db = get_db()
    try:
        users = db.query(User).all()
        return jsonify({
            'success': True,
            'users': [user.to_dict() for user in users]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })
    finally:
        close_db(db)

@app.route('/admin/edit_user', methods=['POST'])
@requires_auth
def edit_user():
    """Edit an existing user."""
    db = get_db()
    try:
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            user_id = data.get('user_id')
            last_name = data.get('last_name')
            email = data.get('email')
            status = data.get('status')
            expiry_date_str = data.get('expiry_date')
            lo_root_ids_str = data.get('lo_root_ids', '')
        else:
            # Handle form data (original format)
            user_id = request.form.get('user_id')
            last_name = request.form.get('last_name')
            email = request.form.get('email')
            status = request.form.get('status')
            expiry_date_str = request.form.get('expiry_date')
            lo_root_ids_str = request.form.get('lo_root_ids', '').strip()

        if not user_id:
            return jsonify({"success": False, "error": "User ID is required"}), 400

        user = User.get_by_id(db, user_id)
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Update basic fields
        if last_name:
            user.last_name = last_name
        if email:
            user.email = email
        if status:
            user.status = status

        # Update expiry date
        if expiry_date_str:
            try:
                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                user.expiry_date = expiry_date
            except ValueError:
                return jsonify({"success": False, "error": "Invalid expiry date format"}), 400

        # Handle LO Root IDs - FIXED PARSING
        # Remove existing LO Root ID associations
        db.query(UserLORootID).filter(UserLORootID.user_id == user.id).delete()

        # Parse and add new LO Root IDs (support both semicolon and comma separation for compatibility)
        if lo_root_ids_str.strip():
            # Split by semicolon first, then by comma as fallback
            if ';' in lo_root_ids_str:
                lo_root_ids = [lo_id.strip() for lo_id in lo_root_ids_str.split(';') if lo_id.strip()]
            else:
                lo_root_ids = [lo_id.strip() for lo_id in lo_root_ids_str.split(',') if lo_id.strip()]
            
            logger.info(f"🔧 Updating user {user_id} LO Root IDs: {lo_root_ids}")

            for lo_root_id in lo_root_ids:
                if lo_root_id:  # Ensure it's not empty
                    association = UserLORootID(user_id=user.id, lo_root_id=lo_root_id)
                    db.add(association)
                    logger.info(f"✅ Added LO Root ID {lo_root_id} for user {user_id}")

        db.commit()
        logger.info(f"Successfully updated user: {user_id}")
        return jsonify({"success": True, "message": "User updated successfully!"})

    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in edit_user: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if db: close_db(db)

@app.route('/debug_quota/<program_code>')
@requires_auth
def debug_quota(program_code):
    """Debug route to check quota system for a specific program"""
    # For admin debugging, we can use a test user ID or current user
    # Since this is an admin route, let's allow specifying a user_id parameter
    user_id = request.args.get('user_id', type=int)
        
    if not user_id:
        return jsonify({"error": "user_id parameter required for debugging"}), 400
    
    db = get_db()
    try:
        # Get chatbot info
        chatbot = ChatbotContent.get_by_code(db, program_code)
        if not chatbot:
            return jsonify({"error": "Program not found"}), 404
            
        # Get all chat history for this user and program
        all_history = db.query(ChatHistory).filter(
            ChatHistory.user_id == user_id,
            ChatHistory.program_code == program_code
        ).order_by(ChatHistory.timestamp.desc()).all()
        
        # Get today's messages using UTC
        today_utc = datetime.utcnow().date()
        today_messages = [h for h in all_history if h.timestamp.date() == today_utc]
        
        debug_info = {
            "program_code": program_code,
            "user_id": user_id,
            "quota": chatbot.quota,
            "total_messages_ever": len(all_history),
            "today_message_count": len(today_messages),
            "remaining_today": max(0, chatbot.quota - len(today_messages)),
            "today_date_utc": today_utc.isoformat(),
            "server_time_utc": datetime.utcnow().isoformat(),
            "recent_messages": [
                {
                    "timestamp": h.timestamp.isoformat(),
                    "date": h.timestamp.date().isoformat(),
                    "user_message": h.user_message[:100] + "..." if len(h.user_message) > 100 else h.user_message
                }
                for h in today_messages[:5]
            ]
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        logger.error(f"Debug quota error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        close_db(db)

# ===== CSV User Synchronization Helper Functions =====

def analyze_csv_user_changes(new_csv_df):
    """
    Analyze new CSV data to create user-to-lo_root_id mapping
    Returns: dict with user email as key and lo_root_ids list as value
    """
    user_lo_mapping = {}
    
    try:
        # Filter for active users only
        active_users = new_csv_df[new_csv_df['status'].str.lower() == 'active']
        
        # Group by user (last_name, email combination)
        user_groups = active_users.groupby(['last_name', 'email'])
        
        for (last_name, email), group in user_groups:
            try:
                last_name = str(last_name).strip()
                email = str(email).strip().lower()
                
                if last_name and email:
                    # Collect all unique lo_root_ids for this user
                    lo_root_ids = []
                    for lo_root_id in group['lo_root_id']:
                        lo_root_id_clean = str(lo_root_id).strip()
                        if lo_root_id_clean and lo_root_id_clean not in lo_root_ids:
                            lo_root_ids.append(lo_root_id_clean)
                    
                    if lo_root_ids:
                        user_lo_mapping[email] = {
                            'last_name': last_name,
                            'email': email,
                            'lo_root_ids': lo_root_ids
                        }
            except Exception as e:
                logger.warning(f"Error processing CSV user group {last_name}, {email}: {e}")
                continue
        
        logger.info(f"Analyzed {len(user_lo_mapping)} active users from CSV")
        return user_lo_mapping
        
    except Exception as e:
        logger.error(f"Error analyzing CSV user changes: {e}")
        return {}

def get_existing_users_lo_mapping(db):
    """
    Get existing users' lo_root_id mapping from database
    Returns: dict with user email as key and current lo_root_ids list as value
    """
    existing_mapping = {}
    
    try:
        users = db.query(User).all()
        for user in users:
            user_lo_ids = [assoc.lo_root_id for assoc in user.lo_root_ids]
            existing_mapping[user.email.lower()] = {
                'user_id': user.id,
                'last_name': user.last_name,
                'email': user.email,
                'lo_root_ids': user_lo_ids
            }
        
        logger.info(f"Found {len(existing_mapping)} existing users in database")
        return existing_mapping
        
    except Exception as e:
        logger.error(f"Error getting existing users mapping: {e}")
        return {}

def sync_user_lo_root_ids(db, csv_user_mapping, existing_user_mapping):
    """
    Compare CSV data with existing user data and perform necessary updates
    Returns: dict with sync statistics
    """
    sync_stats = {
        'users_checked': 0,
        'users_updated': 0,
        'new_lo_ids_added': 0,
        'updated_users': [],
        'errors': []
    }
    
    try:
        for email, csv_user_data in csv_user_mapping.items():
            try:
                sync_stats['users_checked'] += 1
                
                # Find existing user
                if email in existing_user_mapping:
                    existing_user = existing_user_mapping[email]
                    user_id = existing_user['user_id']
                    
                    # Compare current lo_root_ids with new ones
                    current_lo_ids = set(existing_user['lo_root_ids'])
                    new_lo_ids = set(csv_user_data['lo_root_ids'])
                    
                    # Find lo_root_ids that need to be added
                    lo_ids_to_add = new_lo_ids - current_lo_ids
                    
                    if lo_ids_to_add:
                        # Add new lo_root_ids
                        for new_lo_id in lo_ids_to_add:
                            user_lo_association = UserLORootID(
                                user_id=user_id, 
                                lo_root_id=new_lo_id
                            )
                            db.add(user_lo_association)
                            sync_stats['new_lo_ids_added'] += 1
                        
                        sync_stats['users_updated'] += 1
                        sync_stats['updated_users'].append({
                            'email': email,
                            'last_name': existing_user['last_name'],
                            'added_lo_ids': list(lo_ids_to_add)
                        })
                        
                        logger.info(f"Updated user {email}: added lo_root_ids {list(lo_ids_to_add)}")
                        
            except Exception as e:
                error_msg = f"Error syncing user {email}: {str(e)}"
                sync_stats['errors'].append(error_msg)
                logger.error(error_msg)
        
        logger.info(f"Sync completed: {sync_stats['users_updated']} users updated with {sync_stats['new_lo_ids_added']} new access permissions")
        return sync_stats
        
    except Exception as e:
        logger.error(f"Error during user synchronization: {e}")
        sync_stats['errors'].append(f"General sync error: {str(e)}")
        return sync_stats

# Add helper function to convert lo_root_ids to program names
def convert_lo_ids_to_program_names(lo_root_ids):
    """
    Convert lo_root_ids to readable program names
    Returns: list of program names or original lo_root_ids if no mapping found
    """
    db = get_db()
    try:
        program_names = []
        for lo_id in lo_root_ids:
            try:
                # Find chatbot with this lo_root_id
                chatbot_association = db.query(ChatbotLORootAssociation).filter(
                    ChatbotLORootAssociation.lo_root_id == lo_id
                ).first()
                
                if chatbot_association:
                    chatbot = db.query(ChatbotContent).filter(
                        ChatbotContent.id == chatbot_association.chatbot_id
                    ).first()
                    
                    if chatbot:
                        program_names.append(chatbot.display_name or chatbot.name)
                    else:
                        program_names.append(f"Program-{lo_id[:8]}")
                else:
                    program_names.append(f"Program-{lo_id[:8]}")
                    
            except Exception as e:
                print(f"Error converting lo_id {lo_id}: {e}")
                program_names.append(f"Program-{lo_id[:8]}")
                
        return program_names
    except Exception as e:
        print(f"Error in convert_lo_ids_to_program_names: {e}")
        return [f"Program-{lo_id[:8]}" for lo_id in lo_root_ids]
    finally:
        close_db(db)

@app.route('/admin/upload_authorized_users_csv', methods=['POST'])
@requires_auth
def admin_upload_authorized_users_csv():
    """Upload and replace the authorized users CSV file with user synchronization"""
    if 'file' not in request.files:
        session['admin_message'] = 'No file part'
        session['admin_message_type'] = 'error'
        return redirect(url_for('admin'))
    
    file = request.files['file']
    if file.filename == '':
        session['admin_message'] = 'No selected file'
        session['admin_message_type'] = 'error'
        return redirect(url_for('admin'))

    if not file or not file.filename.endswith('.csv'):
        session['admin_message'] = 'Invalid file type. Please upload a CSV file.'
        session['admin_message_type'] = 'error'
        return redirect(url_for('admin'))

    try:
        # Read and validate CSV
        csv_content = file.read().decode('utf-8-sig')
        df = pd.read_csv(StringIO(csv_content))
        
        # Validate required columns
        required_columns = ['last_name', 'email', 'status', 'lo_root_id']
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            error_msg = f'Error: Missing required columns: {", ".join(missing_cols)}'
            session['admin_message'] = error_msg
            session['admin_message_type'] = 'error'
            return redirect(url_for('admin'))
        
        # Filter for active users
        active_df = df[df['status'].str.lower() == 'active']
        if active_df.empty:
            session['admin_message'] = 'Error: No active users found in the CSV file.'
            session['admin_message_type'] = 'error'
            return redirect(url_for('admin'))
        
        # Perform user synchronization before updating CSV
        db = get_db()
        try:
            # Analyze new CSV data
            csv_user_mapping = analyze_csv_user_changes(active_df)
            
            # Get existing user mapping from database
            existing_user_mapping = get_existing_users_lo_mapping(db)
            
            # Perform synchronization
            sync_stats = sync_user_lo_root_ids(db, csv_user_mapping, existing_user_mapping)
            
            # Commit database changes
            db.commit()
            
        except Exception as sync_error:
            if db:
                db.rollback()
            raise sync_error
        finally:
            if db:
                close_db(db)
        
        # Save CSV file using the environment-appropriate path
        csv_file_path = get_csv_file_path()
        df.to_csv(csv_file_path, index=False)
        
        # Clean up any old backup files to save space
        cleanup_old_csv_backups()
        
        # Clear authorized users cache
        clear_authorized_users_cache()
        
        # Prepare success message with sync results
        active_count = len(active_df)
        success_parts = [f'✅ CSV uploaded successfully! {active_count} authorized users loaded.']
        
        if sync_stats["updated_users"]:
            # Convert lo_root_ids to program names for better readability
            updated_details = []
            for user_update in sync_stats["updated_users"][:5]:  # Show first 5
                email = user_update['email']
                lo_ids = user_update['added_lo_ids']
                program_names = convert_lo_ids_to_program_names(lo_ids)
                updated_details.append(f'{email} → {", ".join(program_names)}')
            
            success_parts.append(f'🔄 Synced {len(sync_stats["updated_users"])} existing users with new programs')
            session['admin_sync_details'] = '📋 Updated Users:\n' + '\n'.join(updated_details)
            
            if len(sync_stats["updated_users"]) > 5:
                session['admin_sync_more'] = f'... and {len(sync_stats["updated_users"]) - 5} more users'
        
        success_msg = ' '.join(success_parts)
        session['admin_message'] = success_msg
        session['admin_message_type'] = 'success'
        
        # Handle sync warnings
        if sync_stats["errors"]:
            warning_details = []
            for error in sync_stats["errors"][:3]:  # Show first 3 warnings
                warning_details.append(error)
            session['admin_sync_warnings'] = '⚠️ Sync warnings:\n' + '\n'.join(warning_details)
            
            if len(sync_stats["errors"]) > 3:
                session['admin_sync_warnings_more'] = f'... and {len(sync_stats["errors"]) - 3} more warnings'

    except Exception as e:
        session['admin_message'] = f'Error processing CSV file: {str(e)}'
        session['admin_message_type'] = 'error'
        
    return redirect(url_for('admin'))

@app.route('/admin/download_authorized_users_csv')
@requires_auth
def admin_download_authorized_users_csv():
    """Download the current authorized users CSV file"""
    try:
        csv_file_path = get_csv_file_path()
        if not os.path.exists(csv_file_path):
            flash('No authorized users CSV file found.', 'error')
            return redirect(url_for('admin'))
        
        return send_file(
            csv_file_path,
            as_attachment=True,
            download_name='authorized_users.csv',
            mimetype='text/csv'
        )
    except Exception as e:
        flash(f'Error downloading CSV file: {str(e)}', 'error')
        return redirect(url_for('admin'))

@app.route('/admin/authorized_users_status')
@requires_auth
def admin_authorized_users_status():
    """Get status information about the authorized users CSV"""
    try:
        csv_file_path = get_csv_file_path()
        status_info = {
            "file_exists": os.path.exists(csv_file_path),
            "total_users": 0,
            "active_users": 0,
            "last_modified": None,
            "file_path": csv_file_path,
            "environment": "cloud" if (os.getenv('RENDER') or os.getenv('RAILWAY_STATIC_URL') or os.getenv('HEROKU_APP_NAME')) else "local"
        }
        
        if status_info["file_exists"]:
            # Get file modification time
            mtime = os.path.getmtime(csv_file_path)
            status_info["last_modified"] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            # Load and count users
            authorized_users = load_authorized_users()
            status_info["active_users"] = len(authorized_users)
            
            # Count total users in file
            try:
                df = pd.read_csv(csv_file_path)
                status_info["total_users"] = len(df)
            except Exception:
                pass
        
        return jsonify(status_info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug_user/<int:user_id>')
@requires_auth
def debug_user(user_id):
    """Debug route to check a specific user's lo_root_ids"""
    db = get_db()
    try:
        from sqlalchemy.orm import joinedload
        
        # Get user with explicit lo_root_ids loading
        user = db.query(User).options(joinedload(User.lo_root_ids)).filter(User.id == user_id).first()
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Get raw lo_root_id associations
        raw_associations = db.query(UserLORootID).filter(UserLORootID.user_id == user_id).all()
        
        debug_info = {
            "user_id": user.id,
            "last_name": user.last_name,
            "email": user.email,
            "lo_root_ids_from_relationship": [assoc.lo_root_id for assoc in user.lo_root_ids],
            "lo_root_ids_from_direct_query": [assoc.lo_root_id for assoc in raw_associations],
            "to_dict_result": user.to_dict(),
            "raw_associations_count": len(raw_associations),
            "relationship_count": len(user.lo_root_ids)
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        logger.error(f"Debug user error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        close_db(db)

@app.route('/debug_access_control')
@requires_auth
def debug_access_control():
    """Emergency debug route to check access control state"""
    db = get_db()
    try:
        # Get all users with their LO Root IDs
        users = db.query(User).all()
        user_data = []
        for user in users:
            user_lo_ids = [assoc.lo_root_id for assoc in user.lo_root_ids]
            user_data.append({
                'id': user.id,
                'name': user.last_name,
                'email': user.email,
                'lo_root_ids': user_lo_ids
            })
        
        # Get all chatbots with their LO Root IDs
        chatbots = db.query(ChatbotContent).filter(ChatbotContent.is_active == True).all()
        chatbot_data = []
        for chatbot in chatbots:
            chatbot_lo_ids = [assoc.lo_root_id for assoc in chatbot.lo_root_ids]
            chatbot_data.append({
                'code': chatbot.code,
                'name': chatbot.name,
                'lo_root_ids': chatbot_lo_ids
            })
        
        return jsonify({
            'users': user_data,
            'chatbots': chatbot_data,
            'message': 'Emergency debug data - check console logs'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        close_db(db)

@app.route('/emergency_disable_access_control')
@requires_auth
def emergency_disable_access_control():
    """EMERGENCY: Temporarily disable access control for all chatbots"""
    db = get_db()
    try:
        # Remove all LO Root ID associations from all chatbots
        db.query(ChatbotLORootAssociation).delete()
        db.commit()
        
        # Reload program content
        load_program_content()
        
        logger.warning("🚨 EMERGENCY: Access control disabled for ALL chatbots!")
        return jsonify({
            'success': True, 
            'message': 'EMERGENCY: Access control temporarily disabled. All users can now access all chatbots.'
        })
        
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        close_db(db)

@app.route('/emergency_fix_user_lo_ids')
@requires_auth
def emergency_fix_user_lo_ids():
    """EMERGENCY: Fix malformed LO Root IDs for users"""
    db = get_db()
    try:
        fixed_users = []
        
        # Get all users
        users = db.query(User).all()
        
        for user in users:
            user_lo_ids = [assoc.lo_root_id for assoc in user.lo_root_ids]
            needs_fix = False
            
            # Check for malformed LO Root IDs (containing commas or semicolons)
            for lo_id in user_lo_ids:
                if ',' in lo_id or ';' in lo_id:
                    needs_fix = True
                    logger.warning(f"🔧 Found malformed LO Root ID for user {user.id} ({user.last_name}): {lo_id}")
                    
                    # Delete the malformed association
                    db.query(UserLORootID).filter(
                        UserLORootID.user_id == user.id,
                        UserLORootID.lo_root_id == lo_id
                    ).delete()
                    
                    # Split and add correct IDs
                    if ',' in lo_id:
                        split_ids = [id.strip() for id in lo_id.split(',') if id.strip()]
                    else:
                        split_ids = [id.strip() for id in lo_id.split(';') if id.strip()]
                    
                    for new_id in split_ids:
                        if new_id:  # Ensure it's not empty
                            # Check if this association already exists
                            existing = db.query(UserLORootID).filter(
                                UserLORootID.user_id == user.id,
                                UserLORootID.lo_root_id == new_id
                            ).first()
                            
                            if not existing:
                                new_assoc = UserLORootID(user_id=user.id, lo_root_id=new_id)
                                db.add(new_assoc)
                                logger.info(f"✅ Added correct LO Root ID for user {user.id}: {new_id}")
            
            if needs_fix:
                fixed_users.append({
                    'user_id': user.id,
                    'name': user.last_name,
                    'email': user.email
                })
        
        db.commit()
        
        logger.warning(f"🚨 EMERGENCY FIX: Fixed LO Root IDs for {len(fixed_users)} users")
        return jsonify({
            'success': True,
            'message': f'Fixed LO Root IDs for {len(fixed_users)} users',
            'fixed_users': fixed_users
        })
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error fixing user LO IDs: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        close_db(db)

@app.route('/admin/update_auto_delete_days', methods=['POST'])
@requires_auth  
def admin_update_auto_delete_days():
    """Update auto-delete settings for a chatbot"""
    db = get_db()
    try:
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = request.form.get('chatbot_code') or request.form.get('chatbot_name')
        auto_delete_days = request.form.get('auto_delete_days')
        
        if not chatbot_code:
            return jsonify({"success": False, "error": "Chatbot code is required"}), 400
        
        # Validate and convert auto_delete_days
        if auto_delete_days and auto_delete_days.strip():
            try:
                auto_delete_days = int(auto_delete_days)
                if auto_delete_days <= 0:
                    return jsonify({"success": False, "error": "Auto-delete days must be a positive number"}), 400
            except ValueError:
                return jsonify({"success": False, "error": "Auto-delete days must be a valid number"}), 400
        else:
            auto_delete_days = None  # Disable auto-delete
            
        chatbot = ChatbotContent.get_by_code(db, chatbot_code)
        if not chatbot:
            return jsonify({"success": False, "error": f"Chatbot with code '{chatbot_code}' not found"}), 404
            
        chatbot.auto_delete_days = auto_delete_days
        db.commit()
        
        # Reload content to reflect changes
        load_program_content()
        
        logger.info(f"Successfully updated auto-delete setting for chatbot {chatbot_code}: {auto_delete_days} days")
        
        # Generate user-friendly message
        if auto_delete_days:
            message = f"Auto-delete setting updated: conversations will be automatically deleted after {auto_delete_days} days."
        else:
            message = "Auto-delete disabled: conversations will be kept indefinitely."
        
        return jsonify({
            "success": True, 
            "message": message,
            "auto_delete_text": chatbot.get_auto_delete_text()
        })
        
    except Exception as e:
        if db: db.rollback()
        logger.error(f"Error in admin_update_auto_delete_days: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if db: close_db(db)

def get_deletion_warning_for_user(user_id, program_code):
    """
    Check if user has conversations that will be deleted soon and return warning message
    """
    db = get_db()
    try:
        # Get chatbot info
        chatbot = ChatbotContent.get_by_code(db, program_code)
        if not chatbot or not chatbot.should_auto_delete():
            return None
        
        # Calculate warning period (3 days before deletion)
        warning_days = max(3, chatbot.auto_delete_days // 10)
        deletion_cutoff = datetime.datetime.utcnow() - timedelta(days=chatbot.auto_delete_days)
        warning_cutoff = datetime.datetime.utcnow() - timedelta(days=chatbot.auto_delete_days - warning_days)
        
        # Check for conversations that will be deleted soon
        conversations_at_risk = db.query(ChatHistory).filter(
            and_(
                ChatHistory.user_id == user_id,
                ChatHistory.program_code == program_code.upper(),
                ChatHistory.timestamp < warning_cutoff,
                ChatHistory.timestamp >= deletion_cutoff,  # Not yet eligible for deletion
                ChatHistory.is_visible == True
            )
        ).count()
        
        if conversations_at_risk > 0:
            deletion_date = datetime.datetime.utcnow() + timedelta(days=warning_days)
            return {
                'count': conversations_at_risk,
                'deletion_date': deletion_date.strftime('%B %d, %Y'),
                'days_remaining': warning_days,
                'chatbot_name': chatbot.name
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error checking deletion warning: {e}")
        return None
    finally:
        if db:
            close_db(db)

def get_chat_deletion_info(chat_timestamp, program_code):
    """
    Get deletion information for a specific chat message
    Returns dict with deletion info or None if no auto-delete
    """
    db = get_db()
    try:
        # Get chatbot auto-delete setting
        chatbot = ChatbotContent.get_by_code(db, program_code)
        if not chatbot or not chatbot.should_auto_delete():
            return None
        
        # Calculate deletion date for this specific chat
        deletion_date = chat_timestamp + timedelta(days=chatbot.auto_delete_days)
        days_until_deletion = (deletion_date - datetime.utcnow()).days
        
        return {
            'deletion_date': deletion_date,
            'days_until_deletion': days_until_deletion,
            'auto_delete_days': chatbot.auto_delete_days
        }
    finally:
        close_db(db)

if __name__ == '__main__':
    # Only migrate content if database is empty
    db = get_db()
    try:
        if db.query(ChatbotContent).count() == 0:
            migrate_content_to_db()
    finally:
        close_db(db)
    
    # Then load the content from database
    load_program_content()
    
    # Add user site-packages to sys.path
    sys.path.append(site.getusersitepackages())
    
    # Setup database monitoring
    setup_database_monitoring()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
