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
import markdown2  # Add markdown2 for markdown parsing

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
        available_program_codes = []
        
        for chatbot in chatbots:
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
        
        available_programs.sort(key=lambda x: x["name"])
        
        logger.debug(f"Program select page for user: {session.get('user_id')}, showing {len(available_programs)} programs")
        return render_template('program_select.html', 
                              available_programs=available_programs,
                              available_program_codes=available_program_codes)
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
        result = []
        for h in history:
            # Add user message
            result.append({
                'message': h.user_message,
                'sender': 'user',
                'timestamp': h.timestamp.strftime('%Y-%m-%d %H:%M')
            })
            # Add bot message
            result.append({
                'message': h.bot_message,
                'sender': 'bot',
                'timestamp': h.timestamp.strftime('%Y-%m-%d %H:%M')
            })
        return result
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
    formatted_intro = intro_message.replace("{program}", f"**{program_display_name}**").replace("{quota}", f"**{quota}**")
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
    formatted_intro = intro_message.replace("{program}", f"**{program_display_name}**").replace("{quota}", f"**{quota}**")
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
    formatted_intro = intro_message.replace("{program}", f"**{program_display_name}**").replace("{quota}", f"**{quota}**")
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
        intro_message = chatbot.intro_message if hasattr(chatbot, 'intro_message') and chatbot.intro_message else "Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day."
        user_id = session['user_id']
        chat_history = get_chat_history(user_id, program_upper)
        close_db(db)
        
        # Format the intro message by replacing placeholders
        formatted_intro = intro_message.replace("{program}", f"**{program_display_name}**").replace("{quota}", f"**{quota}**")
        
        return render_template('index.html',
                            program=program_upper,
                            program_display_name=program_display_name,
                            chat_history=chat_history,
                            quota=quota,
                            intro_message=formatted_intro)
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
            ChatHistory.timestamp >= today_start,
            ChatHistory.timestamp <= today_end
        ).count()

        if message_count >= quota:
            return jsonify({"reply": f"You have reached your daily quota of {quota} questions for the {chatbot.name} program. Please try again tomorrow."}), 200

        content_hash = content_hashes.get(current_program)
        if not content_hash:
            content = program_content.get(current_program, "")
            content_hash = get_content_hash(content)
            content_hashes[current_program] = content_hash
            logger.debug(f"Generated new content hash for {current_program}")

        start_time = time.time()
        cache_result = "exact_match"
        
        chatbot_reply = get_cached_response(content_hash, user_message)
        
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
                similar_question = None
        
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
        
        total_time = time.time() - start_time
        logger.info(f"Cache performance: {cache_result} in {total_time:.3f} seconds")

        # Parse markdown in the response
        html_reply = parse_markdown(chatbot_reply)

        # Save to chat history (both user message and chatbot reply)
        chat_entry = ChatHistory(
            user_id=user_id,
            program_code=current_program,
            user_message=user_message,
            bot_message=chatbot_reply
        )
        db.add(chat_entry)
        db.commit()

        # Record conversation in Smartsheet asynchronously
        def record_smartsheet_async(user_question, chatbot_reply, program):
            try:
                record_in_smartsheet(f"[{program}] {user_question}", chatbot_reply)
            except Exception as smex:
                logger.error("Error recording in Smartsheet: %s", str(smex))

        threading.Thread(target=record_smartsheet_async, args=(user_message, chatbot_reply, current_program)).start()

        return jsonify({
            "reply": chatbot_reply,
            "html_reply": html_reply
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
    user_id = session['user_id']
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
            'user_timestamp': current_msg.timestamp.strftime('%Y-%m-%d %H:%M:%S') if current_msg.timestamp else 'N/A',
            'user_name': user_name,
            'user_email': user_email,
            'chatbot_name': chatbot_name_display,
            'user_message': current_msg.user_message,
            'bot_timestamp': current_msg.timestamp.strftime('%Y-%m-%d %H:%M:%S') if current_msg.timestamp else 'N/A',
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

@app.route('/admin/upload', methods=['POST'])
@requires_auth
def admin_upload():
    """Handles the creation of a new chatbot."""
    db = get_db()
    try:
        chatbot_code = request.form.get('course_name')
        display_name = request.form.get('display_name')
        description = request.form.get('description', '')
        category = request.form.get('category', 'standard')
        intro_message = request.form.get('intro_message', 'Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day.')
        default_quota = int(request.form.get('default_quota', 3))
        char_limit = int(request.form.get('char_limit', 50000))
        auto_summarize = request.form.get('auto_summarize', 'true').lower() == 'true'
        final_content = ""
        content_source = "unknown"
        
        # Log what we received for debugging
        logger.info(f"Admin upload - chatbot_code: {chatbot_code}, display_name: {display_name}")
        logger.info(f"Admin upload - char_limit: {char_limit}, auto_summarize: {auto_summarize}, category: {category}")
        logger.info(f"Request form keys: {list(request.form.keys())}")
        if 'files' in request.files:
            logger.info(f"Request has {len(request.files.getlist('files'))} files")
        
        if not chatbot_code or not display_name:
            return jsonify({"success": False, "error": "Chatbot ID (course_name) and Display Name are required."}), 400
        
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
                    "warning": f"Content length ({len(final_content):,} characters) exceeds the specified limit ({char_limit:,} characters).",
                    "content_length": len(final_content),
                    "char_limit": char_limit
                }), 400

        # Create new chatbot (or update if editing)
        logger.info(f"Creating chatbot with final content length: {len(final_content)}")
        logger.info(f"Content source was: {content_source}")
        new_chatbot = ChatbotContent.create_or_update(
            db=db,
            code=chatbot_code.upper(),
            name=display_name,
            content=final_content,
            description=description,
            quota=default_quota,
            intro_message=intro_message,
            char_limit=char_limit,
            is_active=True, # New chatbots are active by default
            category=category
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
            "char_limit": chatbot.char_limit
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

def gpt_summarize_text(text, target_length=None, max_length=50000):
    """
    Use GPT-4o-mini to intelligently summarize text to meet a target length.
    
    Args:
        text (str): The input text to summarize
        target_length (int, optional): Target character length. If None, defaults to 80% of max_length
        max_length (int): Maximum allowed length
        
    Returns:
        str: Summarized text within the target length
        float: Percent reduction achieved
    """
    if not text:
        return "", 0
    
    # If text is already shorter than max_length, return as is
    if len(text) <= max_length:
        return text, 0
    
    if target_length is None:
        target_length = int(max_length * 0.95)  # 95% of max to leave minimal buffer and maximize content preservation
    
    original_length = len(text)
    logger.info(f"Starting GPT summarization: {original_length} characters to target {target_length} characters")
    
    # Keep most of the original text and only do minimal cleanup
    # Only fix multiple newlines (3+) and multiple spaces to avoid confusing the model
    cleaned_text = re.sub(r'\n{4,}', '\n\n\n', text)  # Keep more line breaks for structure
    cleaned_text = re.sub(r' {3,}', '  ', cleaned_text)  # Keep double spaces for formatting
    
    # Only remove critical confidentiality notices that don't affect content
    minimal_boilerplate = [
        r'(?i)confidential.*?this email.*?intended only for',  # Email confidentiality notices
        r'(?i)proprietary notice.*?distribution is prohibited',  # Distribution prohibitions
    ]
    
    for pattern in minimal_boilerplate:
        cleaned_text = re.sub(pattern, '[Legal notice removed]', cleaned_text)
        
    # For direct GPT summarization, always minimize the perceived reduction needed
    current_length = len(cleaned_text)
    
    # Use a fixed target length close to the maximum to ensure minimal content loss
    if current_length > 50000:
        target_length = 50000  # Maximum target for very large documents
    elif current_length > target_length:
        # For documents that need reduction, set target to at least 80% of current length
        # This ensures we keep as much content as possible while still reducing
        target_length = max(target_length, int(current_length * 0.8))
    
    # Calculate a conservative reduction factor to preserve more content
    reduction_factor = max(0.1, min(0.3, 1 - (target_length / current_length)))  # Cap at 0.3 (30% reduction)
    
    # Prepare system prompt based on reduction factor
    prompt_instructions = ""
    if reduction_factor <= 0.3:
        prompt_instructions = "Maintain almost all of the original content. Only remove clear redundancies while preserving all details, examples and context."
    elif reduction_factor <= 0.5:
        prompt_instructions = "Maintain most of the original content, keeping all important details and examples. Only condense verbose explanations."
    elif reduction_factor <= 0.7:
        prompt_instructions = "Keep most core concepts and important details, while condensing explanations and examples."
    else:
        prompt_instructions = "Focus on preserving main ideas and key points, condensing where possible but maintaining overall scope and depth."
        
    # Format system prompt
    system_prompt = f"""You are a text summarization assistant. Summarize the provided text while preserving as much original content as possible. 
The output should be approximately {target_length} characters in length (current text is {current_length} characters).
{prompt_instructions}

IMPORTANT GUIDELINES:
1. Preserve ALL important facts, key concepts, definitions, and essential information without exception
2. Maintain the original document's complete structure, sections, and flow
3. Keep ALL section titles, headers, and subheaders exactly as they appear
4. Remove only clear redundancies and extremely verbose explanations if necessary
5. Do not add any of your own commentary or content not present in the original
6. The summary should aim for approximately {target_length} characters, but prioritize content preservation over length
7. Do not include phrases like "the text discusses" - present the content directly
8. Do not begin with "Here is the summarized content" or similar meta-commentary
9. Preserve ALL technical details, numbers, statistics, names, and specific information
10. The summary must be a comprehensive, cohesive document that captures the full scope of the original
11. Aim to keep at least 50% of the original paragraphs mostly intact"""

    # Format user prompt - ask for longer summary to ensure we get enough content
    user_prompt = f"Please summarize the following text to approximately {target_length} characters. Your goal is to preserve as much of the original content, structure, and details as possible. The summary should be comprehensive and maintain all key information:\n\n{cleaned_text}"

    # Call the GPT-4o-mini API
    try:
        logger.info("Calling GPT-4o-mini API for content summarization")
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,  # Lower temperature for more consistent summaries
            max_tokens=16384,  # GPT-4o-mini's max supported tokens
            n=1,
        )
        
        # Extract summary from the response
        summary = response['choices'][0]['message']['content'].strip()
        
        # Log completion and token usage
        final_length = len(summary)
        percent_reduced = round(((original_length - final_length) / original_length) * 100, 1)
        logger.info(f"GPT summary complete: {original_length} → {final_length} chars ({percent_reduced}% reduction)")
        
        if 'usage' in response:
            prompt_tokens = response['usage']['prompt_tokens']
            completion_tokens = response['usage']['completion_tokens']
            total_tokens = response['usage']['total_tokens']
            logger.info(f"Token usage: {prompt_tokens} prompt + {completion_tokens} completion = {total_tokens} total")
        
        # Check if summary is within target length
        if len(summary) > target_length:
            logger.warning(f"Generated summary ({len(summary)} chars) exceeds target length ({target_length}). Will trim.")
            # Simple trimming if necessary
            summary = summary[:target_length - 100] + "..."
            
        return summary, percent_reduced
        
    except Exception as e:
        logger.error(f"Error in GPT summarization: {str(e)}")
        # Fall back to rule-based summarization if GPT fails
        logger.info("Falling back to rule-based summarization")
        result = smart_text_summarization(text, target_length, max_length)
        percent_reduced = round(((original_length - len(result)) / original_length) * 100, 1)
        return result, percent_reduced

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