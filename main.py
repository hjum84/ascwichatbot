import openai
import os
import datetime
import smartsheet
import csv
import io
import threading
import logging
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, redirect, url_for, make_response, Response, session, flash
from functools import wraps
import re
from models import User, ChatbotContent, get_db, close_db, ChatHistory
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
from sqlalchemy import func

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

def find_similar_question(user_message, content_hash):
    """
    Find a question similar to the given user_message.
    Returns a cached question within the content_hash that has similarity above threshold.
    """
    # Basic preprocessing: lowercase, normalize whitespace
    normalized_question = re.sub(r'\s+', ' ', user_message.lower()).strip()
    
    # Create cache key
    cache_key = f"{content_hash}:{normalized_question}"
    
    # Check if we already found similar questions in cache
    if cache_key in similar_questions_cache:
        logger.debug(f"Similar question cache hit for: {normalized_question[:30]}...")
        return similar_questions_cache[cache_key]
    
    # Generate embedding for new question
    new_embedding = get_embedding(normalized_question)
    if new_embedding is None:
        return None
    
    # Construct a list to hold questions from cache keys
    content_questions = []
    
    # Get cache info
    cache_info = get_cached_response.cache_info()
    # Extract the cache dictionary
    if hasattr(cache_info, '_cache'):
        cache_dict = cache_info._cache
    else:
        # For some Python versions, it might be just .cache
        cache_dict = get_cached_response.cache
    
    # Find existing questions for this content_hash
    for key in cache_dict:
        if key[0] == content_hash:  # Only consider entries with matching content_hash
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
                logger.debug(f"Found similar question: '{question}' for '{normalized_question}' with similarity {similarity:.3f}")
        except Exception as e:
            logger.error(f"Error calculating similarity between embeddings: {str(e)}")
            continue
    
    # Store in similar questions cache
    similar_questions_cache[cache_key] = best_question
    
    # If we found a similar question, return it
    return best_question

@lru_cache(maxsize=1000)
def get_cached_response(content_hash, user_message):
    """Get cached response for the same content and user message.
    This function is decorated with lru_cache which will cache the results,
    reducing API costs by using cached inputs (50% cost reduction).
    """
    # Find program code based on content hash
    program_code = None
    for code, hash_value in content_hashes.items():
        if hash_value == content_hash:
            program_code = code
            break
    
    if not program_code or program_code not in program_content:
        logger.error(f"Program content not found for hash: {content_hash}")
        return None
    
    try:
        # Get actual content to use in system message
        content = program_content[program_code]
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You are an assistant that only answers questions based on the following content for the {program_names.get(program_code, 'selected')} program: {content}"},
                {"role": "user", "content": user_message}
            ],
            max_tokens=500
        )
        return response['choices'][0]['message']['content'].strip()
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
            content_hashes[chatbot.code] = get_content_hash(chatbot.content)
        
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
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
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

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        
        db = get_db()
        try:
            logger.debug("Creating new user with email: %s", email)
            new_user = User(last_name=last_name, email=email)
            db.add(new_user)
            db.commit()
            logger.debug("User created successfully")
            close_db(db)
            return redirect(url_for('login'))
        except Exception as e:
            db.rollback()
            logger.error("Registration error: %s", str(e))
            close_db(db)
            return f"Registration error: {str(e)}", 400
            
    return render_template('register.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, redirect to program_select
    if 'user_id' in session:
        return redirect(url_for('program_select'))
    if request.method == 'POST':
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        
        logger.debug("Login attempt for email: %s", email)
        
        # Get DB session
        db = get_db()
        try:
            # Query user with class method
            user = User.get_by_credentials(db, last_name, email)
            
            if not user:
                logger.debug("User not found")
                close_db(db)
                flash("User not found. Please register first.", "danger")
                return redirect(url_for('login'))
                
            # Update visit count
            logger.debug("User found with ID: %s", user.id)
            user.visit_count += 1
            
            # Store data before committing
            user_data = user.to_dict()
            
            # Commit changes safely
            db.commit()
            
            # Store in session
            session['user_id'] = user_data['id']
            session['user_email'] = user_data['email']
            session['last_name'] = user_data['last_name']
            
            # Cleanup
            close_db(db)
            
            # Always direct users to program selection after login
            # This ensures they can choose their program every time
            logger.debug("Redirecting to program selection after login")
            return redirect(url_for('program_select'))
                
        except Exception as e:
            # Rollback on error
            db.rollback()
            close_db(db)
            logger.error("Login error: %s", str(e))
            return f"Login error: {str(e)}", 500
            
    # GET request - show login form
    return render_template('login.html')

# Program selection route
@app.route('/program_select')
@login_required
def program_select():
    # Verify user is logged in (handled by decorator)
    # Get all available programs from database
    db = get_db()
    try:
        chatbots = ChatbotContent.get_all_active(db)
        
        available_programs = []
        for chatbot in chatbots:
            # Determine if NEW badge should be shown
            show_new = False
            if chatbot.created_at:
                # Show NEW if created within the last 7 days
                if (datetime.now() - chatbot.created_at).days < 7:
                    show_new = True
            
            # Ensure predefined programs BCC, MI, Safety do not show 'NEW' badge
            if chatbot.code in ['BCC', 'MI', 'SAFETY']:
                show_new = False

            program_info = {
                "code": chatbot.code,
                "name": chatbot.name,
                "description": chatbot.description or f"Learn about the {chatbot.name} program content.",
                "show_new_badge": show_new 
            }
            available_programs.append(program_info)
        
        available_programs.sort(key=lambda x: x["name"])
        
        logger.debug(f"Program select page for user: {session.get('user_id')}, showing {len(available_programs)} programs")
        return render_template('program_select.html', 
                                available_programs=available_programs)
    finally:
        close_db(db)

# Set program route
@app.route('/set_program/<program>')
@login_required
def set_program(program):
    # Verify if content exists for this program in the database
    program_upper = program.upper()
    db = get_db()
    try:
        chatbot = ChatbotContent.get_by_code(db, program_upper)
        if not chatbot or not chatbot.is_active:
            logger.warning(f"Attempt to access non-existent program: {program}")
            close_db(db)
            return redirect(url_for('program_select'))
            
        # Verify user is logged in
        if 'user_id' not in session:
            logger.warning("User not in session, redirecting to login")
            close_db(db)
            return redirect(url_for('login'))
            
        user_id = session['user_id']
        logger.debug("Setting program %s for user %s", program, user_id)
        
        # Get user by ID
        user = User.get_by_id(db, user_id)
        
        if not user:
            logger.warning("User not found in database")
            close_db(db)
            # Clear session and redirect to login
            session.clear()
            return redirect(url_for('login'))
            
        # Update program
        user.current_program = program_upper
        db.commit()
        
        # Set in session
        session['current_program'] = program_upper
        
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

# Helper: fetch chat history for a user and program

def get_chat_history(user_id, program_code, limit=50):
    db = get_db()
    try:
        history = db.query(ChatHistory).filter(
            ChatHistory.user_id == user_id,
            ChatHistory.program_code == program_code,
            ChatHistory.is_visible == True
        ).order_by(ChatHistory.timestamp.asc()).limit(limit).all()
        return [
            {
                'message': h.message,
                'sender': h.sender,
                'timestamp': h.timestamp.strftime('%Y-%m-%d %H:%M')
            } for h in history
        ]
    finally:
        close_db(db)

# BCC Chatbot interface
@app.route('/index_bcc')
@login_required
def index_bcc():
    session['current_program'] = 'BCC'
    user_id = session['user_id']
    chat_history = get_chat_history(user_id, 'BCC')
    db = get_db()
    try:
        chatbot = ChatbotContent.get_by_code(db, 'BCC')
        quota = chatbot.quota if chatbot else 3
        program_display_name = chatbot.name if chatbot else "Building Coaching Competency"
        intro_message = chatbot.intro_message if chatbot else "Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day."
    finally:
        close_db(db)
    # Format the intro message by replacing placeholders
    formatted_intro = intro_message.replace("{program}", program_display_name).replace("{quota}", str(quota))
    return render_template('index.html',
                         program='BCC',
                         program_display_name=program_display_name,
                         chat_history=chat_history,
                         quota=quota,
                         intro_message=formatted_intro)

# MI Chatbot interface
@app.route('/index_mi')
@login_required
def index_mi():
    session['current_program'] = 'MI'
    user_id = session['user_id']
    chat_history = get_chat_history(user_id, 'MI')
    db = get_db()
    try:
        chatbot = ChatbotContent.get_by_code(db, 'MI')
        quota = chatbot.quota if chatbot else 3
        program_display_name = chatbot.name if chatbot else "Motivational Interviewing"
        intro_message = chatbot.intro_message if chatbot else "Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day."
    finally:
        close_db(db)
    # Format the intro message by replacing placeholders
    formatted_intro = intro_message.replace("{program}", program_display_name).replace("{quota}", str(quota))
    return render_template('index.html',
                         program='MI',
                         program_display_name=program_display_name,
                         chat_history=chat_history,
                         quota=quota,
                         intro_message=formatted_intro)

# Safety Chatbot interface
@app.route('/index_safety')
@login_required
def index_safety():
    session['current_program'] = 'Safety'
    user_id = session['user_id']
    chat_history = get_chat_history(user_id, 'Safety')
    db = get_db()
    try:
        chatbot = ChatbotContent.get_by_code(db, 'Safety')
        quota = chatbot.quota if chatbot else 3
        program_display_name = chatbot.name if chatbot else "Safety and Risk Assessment"
        intro_message = chatbot.intro_message if chatbot else "Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day."
    finally:
        close_db(db)
    # Format the intro message by replacing placeholders
    formatted_intro = intro_message.replace("{program}", program_display_name).replace("{quota}", str(quota))
    return render_template('index.html',
                         program='Safety',
                         program_display_name=program_display_name,
                         chat_history=chat_history,
                         quota=quota,
                         intro_message=formatted_intro)

# Generic chatbot interface for custom programs
@app.route('/index_generic/<program>')
@login_required
def index_generic(program):
    program_upper = program.upper()
    db = get_db()
    try:
        chatbot = ChatbotContent.get_by_code(db, program_upper)
        if not chatbot or not chatbot.is_active:
            logger.warning(f"Attempt to access non-existent program: {program}")
            close_db(db)
            return redirect(url_for('program_select'))
        session['current_program'] = program_upper
        program_display_name = chatbot.name
        quota = chatbot.quota
        user_id = session['user_id']
        chat_history = get_chat_history(user_id, program_upper)
        close_db(db)
        return render_template('index.html',
                            program=program_upper,
                            program_display_name=program_display_name,
                            chat_history=chat_history,
                            quota=quota)
    except Exception as e:
        if 'db' in locals():
            close_db(db)
        logger.error(f"Error loading generic chatbot: {str(e)}")
        return redirect(url_for('program_select'))

# Legacy index route - redirect to program selection
@app.route('/index')
def index():
    # If somehow users reach this route, redirect to program selection
    logger.debug("Redirecting from legacy index route to program selection")
    return redirect(url_for('program_select'))

# Chat endpoint for processing user messages
@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_message = request.json.get("message")
    if not user_message:
        return jsonify({"error": "A question is required."}), 400

    current_program = session.get('current_program', 'BCC')
    user_id = session['user_id']
    db = get_db()
    try:
        # Get the chatbot's quota from database
        chatbot = ChatbotContent.get_by_code(db, current_program)
        if not chatbot:
            return jsonify({"error": "Program not found."}), 404
        
        quota = chatbot.quota

        # Count today's messages for this user and program
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        
        message_count = db.query(ChatHistory).filter(
            ChatHistory.user_id == user_id,
            ChatHistory.program_code == current_program,
            ChatHistory.sender == 'user',
            ChatHistory.timestamp >= today_start,
            ChatHistory.timestamp <= today_end
        ).count()

        # Check if quota exceeded
        if message_count >= quota:
            return jsonify({"reply": f"You have reached your daily quota of {quota} questions for the {chatbot.name} program. Please try again tomorrow."}), 200

        # Save user message to chat history
        user_history = ChatHistory(
            user_id=user_id,
            program_code=current_program,
            message=user_message,
            sender='user'
        )
        db.add(user_history)
        db.commit()

        # Get content hash for the current program
        content_hash = content_hashes.get(current_program)
        if not content_hash:
            content = program_content.get(current_program, "")
            content_hash = get_content_hash(content)
            content_hashes[current_program] = content_hash
            logger.debug(f"Generated new content hash for {current_program}")

        # Track cache performance
        start_time = time.time()
        cache_result = "exact_match"
        
        # Try to get cached response first (exact match)
        chatbot_reply = get_cached_response(content_hash, user_message)
        
        # If no exact match, try to find semantically similar question
        if not chatbot_reply:
            cache_result = "semantic_match"
            try:
                similar_question = find_similar_question(user_message, content_hash)
                if similar_question:
                    logger.debug(f"Using semantically similar question: '{similar_question}' instead of '{user_message}'")
                    chatbot_reply = get_cached_response(content_hash, similar_question)
                    logger.debug(f"Retrieved response for semantically similar question in {time.time() - start_time:.3f} seconds")
            except Exception as e:
                logger.error(f"Error finding similar question: {str(e)}")
                # Continue without similar questions if this fails
                similar_question = None
        
        # If no cached response at all, get new response
        if not chatbot_reply:
            cache_result = "cache_miss"
            try:
                logger.debug(f"Cache miss for {current_program}, getting new response")
                response = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": f"You are an assistant that only answers questions based on the following content for the {program_names.get(current_program, 'selected')} program: {program_content.get(current_program, '')}"},
                        {"role": "user", "content": user_message}
                    ],
                    max_tokens=500
                )
                chatbot_reply = response['choices'][0]['message']['content'].strip()
            except Exception as e:
                logger.error(f"Error getting new response: {str(e)}")
                return jsonify({"error": str(e)}), 500
        
        # Log cache performance
        total_time = time.time() - start_time
        logger.info(f"Cache performance: {cache_result} in {total_time:.3f} seconds")

        # Truncate response to 300 words if necessary
        words = chatbot_reply.split()
        if len(words) > 500:
            truncated_text = ' '.join(words[:300])
            end_index = chatbot_reply.find(truncated_text) + len(truncated_text)
            rest_text = chatbot_reply[end_index:]
            sentence_end = re.search(r'[.?!]', rest_text)
            if sentence_end:
                chatbot_reply = chatbot_reply[:end_index + sentence_end.end()]
            else:
                chatbot_reply = truncated_text

        # Save bot reply to chat history
        bot_history = ChatHistory(
            user_id=user_id,
            program_code=current_program,
            message=chatbot_reply,
            sender='bot'
        )
        db.add(bot_history)
        db.commit()

        # Record conversation in Smartsheet asynchronously
        def record_smartsheet_async(user_question, chatbot_reply, program):
            try:
                record_in_smartsheet(f"[{program}] {user_question}", chatbot_reply)
            except Exception as smex:
                logger.error("Error recording in Smartsheet: %s", str(smex))

        threading.Thread(target=record_smartsheet_async, args=(user_message, chatbot_reply, current_program)).start()

        return jsonify({"reply": chatbot_reply})

    except Exception as e:
        if 'db' in locals():
            db.rollback()
        logger.error(f"Error in chat endpoint: {str(e)}")
        return jsonify({"error": "An error occurred while processing your request. Please try again."}), 500
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
    session.pop('user_id', None)
    session.pop('user_email', None)
    session.pop('last_name', None)
    session.pop('current_program', None)
    # session.clear() # Alternatively, clear the entire session
    flash('You have been successfully logged out.', 'success')
    return redirect(url_for('login'))

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
        user = db.query(User).filter(User.email == email, User.last_name == last_name).first()
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
    db = get_db()
    try:
        # Get all users and convert to dictionaries
        users = db.query(User).all()
        user_data = [user.to_dict() for user in users]
        
        # Create CSV output
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Last Name', 'Email', 'Visit Count', 'Program'])
        
        for user in user_data:
            writer.writerow([user['id'], user['last_name'], user['email'], user['visit_count'], user['current_program']])
        
        close_db(db)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=user_data.csv"}
        )
    except Exception as e:
        logger.error("Error exporting users: %s", str(e))
        close_db(db)
        return f"Error exporting users: {str(e)}", 500

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
                self.current_program = data['current_program']
                
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
    """Fetch and pair user questions with subsequent bot answers (robust version, ascending order)."""
    # Use timestamp ASC to get the oldest conversations first
    history_query = db.query(ChatHistory).order_by(
        ChatHistory.timestamp.asc()
    )

    # Calculate total count for pagination
    total_count = history_query.count()
    total_pages = (total_count + per_page - 1) // per_page  # Ceiling division
    
    # Apply pagination
    offset = (page - 1) * per_page
    history = history_query.offset(offset).limit(per_page * 10).all()  # Fetch more to ensure pairs

    paired_conversations = []
    used_bot_ids = set()
    i = 0
    while i < len(history):
        current_msg = history[i]
        if current_msg.sender == 'user':
            user_obj = db.query(User).filter(User.id == current_msg.user_id).first()
            chatbot_obj = db.query(ChatbotContent).filter(ChatbotContent.code == current_msg.program_code).first()

            user_name = user_obj.last_name if user_obj else 'Unknown'
            user_email = user_obj.email if user_obj else 'Unknown'
            chatbot_name_display = chatbot_obj.name if chatbot_obj else current_msg.program_code

            pair_data = {
                'user_timestamp': current_msg.timestamp.strftime('%Y-%m-%d %H:%M:%S') if current_msg.timestamp else 'N/A',
                'user_name': user_name,
                'user_email': user_email,
                'chatbot_name': chatbot_name_display,
                'user_message': current_msg.message,
                'bot_timestamp': 'N/A',
                'bot_message': 'No reply found.'
            }

            # Find the next bot reply for this user/program that hasn't been paired yet
            for j in range(i+1, len(history)):
                next_msg = history[j]
                if (
                    next_msg.sender == 'bot' and
                    next_msg.user_id == current_msg.user_id and
                    next_msg.program_code == current_msg.program_code and
                    next_msg.id not in used_bot_ids and
                    next_msg.timestamp > current_msg.timestamp
                ):
                    pair_data['bot_timestamp'] = next_msg.timestamp.strftime('%Y-%m-%d %H:%M:%S') if next_msg.timestamp else 'N/A'
                    pair_data['bot_message'] = next_msg.message
                    used_bot_ids.add(next_msg.id)
                    break

            paired_conversations.append(pair_data)
        i += 1
        if len(paired_conversations) >= per_page:
            break
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

        # If search parameters are present, filter the conversations
        if search_term_param or chatbot_code_param:
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

                if match_search and match_chatbot:
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
            query = query.filter(ChatHistory.message.ilike(f'%{search_term}%'))
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
            result.append({
                'id': conv.id,
                'user_name': user.last_name if user else 'Unknown',
                'user_email': user.email if user else 'Unknown',
                'chatbot_name': chatbot.name if chatbot else conv.program_code,
                'message': conv.message,
                'sender': conv.sender,
                'timestamp': conv.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({"success": True, "conversations": result})
        
    finally:
        close_db(db)

def get_available_chatbots():
    """Get all active chatbots from the database."""
    db = get_db()
    try:
        chatbots = db.query(ChatbotContent).filter(ChatbotContent.is_active == True).all()
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
        users = db.query(User).all()
        return [user.to_dict() for user in users]
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
            result.append({
                'id': conv.id,
                'user_id': conv.user_id,
                'user_name': user.last_name if user else 'Unknown',
                'user_email': user.email if user else 'Unknown',
                'chatbot_name': chatbot_content.name if chatbot_content else conv.program_code,
                'message': conv.message,
                'sender': conv.sender,
                'timestamp': conv.timestamp.strftime('%Y-%m-%d %H:%M:%S') if conv.timestamp else 'N/A' # Format timestamp
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


@app.route('/admin/preview_upload', methods=['POST'])
@requires_auth
def admin_preview_upload():
    """Handles file uploads for previewing content before chatbot creation."""
    if 'files' not in request.files:
        return jsonify({"success": False, "error": "No files provided for preview."}), 400

    files = request.files.getlist('files')
    char_limit = int(request.form.get('char_limit', 50000))
    
    # For edit modal scenario
    current_content_text = request.form.get('current_content', '')
    append_content_flag = request.form.get('append_content', 'false').lower() == 'true'

    extracted_files_data = []
    combined_text_parts = []

    if append_content_flag and current_content_text:
        combined_text_parts.append(current_content_text)

    for file_storage in files:
        if file_storage and file_storage.filename:
            text = extract_text_from_file(file_storage)
            extracted_files_data.append({
                "filename": secure_filename(file_storage.filename),
                "content": text,
                "char_count": len(text)
            })
            combined_text_parts.append(text)
        else:
            logger.warning("Empty file storage object received in preview_upload.")


    combined_preview_content = "\\n\\n".join(combined_text_parts)
    total_char_count = len(combined_preview_content)
    exceeds_limit = total_char_count > char_limit
    warning_message = ""
    if exceeds_limit:
        warning_message = f"Content ({total_char_count:,} chars) exceeds limit of {char_limit:,} chars."

    return jsonify({
        "success": True,
        "files": extracted_files_data,
        "combined_preview": combined_preview_content,
        "total_char_count": total_char_count,
        "char_limit": char_limit,
        "exceeds_limit": exceeds_limit,
        "warning": warning_message
    })

@app.route('/admin/upload', methods=['POST'])
@requires_auth
def admin_upload():
    """Handles the creation of a new chatbot."""
    db = get_db()
    try:
        chatbot_code = request.form.get('course_name')
        display_name = request.form.get('display_name')
        description = request.form.get('description', '')
        intro_message = request.form.get('intro_message', 'Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day.')
        default_quota = int(request.form.get('default_quota', 3))
        char_limit = int(request.form.get('char_limit', 50000))
        
        use_edited_content = request.form.get('use_edited_content', 'false').lower() == 'true'
        final_content = ""

        if not chatbot_code or not display_name:
            return jsonify({"success": False, "error": "Chatbot ID (course_name) and Display Name are required."}), 400
        
        # Check if chatbot code already exists
        existing_chatbot = ChatbotContent.get_by_code(db, chatbot_code.upper())
        if existing_chatbot:
            return jsonify({"success": False, "error": f"Chatbot with ID '{chatbot_code}' already exists. Please use a unique ID."}), 400

        if use_edited_content:
            final_content = request.form.get('combined_content', '')
        else:
            files = request.files.getlist('files') # Changed from 'file' to 'files' based on JS
            if not files or all(not f.filename for f in files):
                 return jsonify({"success": False, "error": "No files uploaded."}), 400
            
            content_parts = []
            for file_storage in files:
                if file_storage and file_storage.filename:
                    text = extract_text_from_file(file_storage)
                    content_parts.append(text)
            final_content = "\\n\\n".join(content_parts)

        if len(final_content) > char_limit:
            return jsonify({
                "success": False, 
                "error": "Content too long",
                "warning": f"Content length ({len(final_content):,} characters) exceeds the specified limit ({char_limit:,} characters).",
                "content_length": len(final_content),
                "char_limit": char_limit
            }), 400

        if not final_content.strip():
             return jsonify({"success": False, "error": "Extracted content is empty. Please check your files."}), 400

        # Create new chatbot
        new_chatbot = ChatbotContent.create_or_update(
            db=db,
            code=chatbot_code.upper(),
            name=display_name,
            content=final_content,
            description=description,
            quota=default_quota,
            intro_message=intro_message,
            char_limit=char_limit,
            is_active=True # New chatbots are active by default
        )
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

        # Permanently delete the chatbot
        db.delete(chatbot)
        db.commit()
        
        # Also update the in-memory program content
        load_program_content()

        logger.info(f"Successfully permanently deleted chatbot: {chatbot_code}")
        return jsonify({"success": True, "message": "Chatbot permanently deleted successfully!"})

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

@app.route('/admin/get_chatbot_content', methods=['GET'])
@requires_auth
def admin_get_chatbot_content():
    """Get the content of a chatbot for editing (admin route)."""
    db = get_db()
    try:
        # Accept both chatbot_code and chatbot_name for compatibility
        chatbot_code = request.args.get('chatbot_code') or request.args.get('chatbot_name')
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
        logger.error(f"Error in admin_update_chatbot_content: {e}", exc_info=True)
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
