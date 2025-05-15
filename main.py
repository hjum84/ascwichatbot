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

# Load content summaries for each program from database
def load_program_content():
    # Clear existing content
    program_content.clear()
    program_names.clear()
    program_descriptions.clear()
    deleted_programs.clear()  # Clear deleted programs set
    
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
            'value': datetime.datetime.now().isoformat()
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
                if (datetime.datetime.utcnow() - chatbot.created_at).days < 7:
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
    finally:
        close_db(db)
    return render_template('index.html',
                         program='BCC',
                         program_display_name=program_display_name,
                         chat_history=chat_history,
                         quota=quota)

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
    finally:
        close_db(db)
    return render_template('index.html',
                         program='MI',
                         program_display_name=program_display_name,
                         chat_history=chat_history,
                         quota=quota)

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
    finally:
        close_db(db)
    return render_template('index.html',
                         program='Safety',
                         program_display_name=program_display_name,
                         chat_history=chat_history,
                         quota=quota)

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
        today = datetime.datetime.utcnow().date()
        today_start = datetime.datetime.combine(today, datetime.time.min)
        today_end = datetime.datetime.combine(today, datetime.time.max)
        
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

        # Get content for the selected program
        content = program_content.get(current_program, "Content not available for this program")

        try:
            # Create a system message specific to the current program
            system_message = f"You are an assistant that only answers questions based on the following content for the {program_names.get(current_program, 'selected')} program: {content}"
            logger.debug(f"Using content for program: {current_program}")
            
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=500
            )
            
            chatbot_reply = response['choices'][0]['message']['content'].strip()

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
            db.rollback()
            logger.error("Chat error: %s", str(e))
            return jsonify({"error": str(e)}), 500

    except Exception as e:
        if 'db' in locals():
            db.rollback()
        logger.error(f"Error in chat endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500
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

# Admin page route
@app.route('/admin')
@requires_auth
def admin():
    # Get list of available and deleted chatbots from database
    db = get_db()
    try:
        # Get active chatbots
        active_chatbots = ChatbotContent.get_all_active(db)
        available_chatbots = []
        for chatbot in active_chatbots:
            available_chatbots.append({
                "name": chatbot.code,
                "display_name": chatbot.name,
                "description": chatbot.description or "",
                "quota": chatbot.quota  # Add quota here
            })
        
        # Get inactive (deleted) chatbots
        deleted_chatbots = []
        deleted_bots = db.query(ChatbotContent).filter(ChatbotContent.is_active == False).all()
        for chatbot in deleted_bots:
            deleted_chatbots.append({
                "name": chatbot.code,
                "display_name": chatbot.name
            })
        
        return render_template('admin.html', 
                              available_chatbots=available_chatbots,
                              deleted_chatbots=deleted_chatbots,
                              message=request.args.get('message'),
                              message_type=request.args.get('message_type', 'info'))
    finally:
        close_db(db)

def clean_text(text):
    """Clean and normalize text content by removing unnecessary elements."""
    # Remove multiple newlines
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    # Remove page numbers (e.g., "Page 1 of 10")
    text = re.sub(r'Page\s+\d+\s+of\s+\d+', '', text)
    
    # Remove headers and footers (common patterns)
    text = re.sub(r'^.*?©.*?$', '', text, flags=re.MULTILINE)  # Copyright notices
    text = re.sub(r'^.*?Confidential.*?$', '', text, flags=re.MULTILINE)  # Confidential notices
    
    # Remove repeated headers (e.g., "Chapter 1" appearing multiple times)
    text = re.sub(r'(^.*?$)\n\1', r'\1', text, flags=re.MULTILINE)
    
    # Remove empty lines at the beginning and end
    text = text.strip()
    
    # Remove multiple spaces
    text = re.sub(r' +', ' ', text)
    
    # Remove special characters that might be artifacts from PDF/PPT conversion
    text = re.sub(r'[^\S\n]+', ' ', text)  # Keep newlines but remove other whitespace
    
    return text

@app.route('/admin_upload', methods=['POST'])
@requires_auth
def admin_upload():
    try:
        logger.info("Admin upload route called")
        logger.info(f"Request method: {request.method}")
        logger.info(f"Content type: {request.content_type}")
        logger.info(f"Form data: {request.form}")
        logger.info(f"Files: {request.files}")
        
        # Get course name
        course_name = request.form.get('course_name')
        logger.info(f"Course name received: {course_name}")
        
        if not course_name:
            logger.warning("No course name provided")
            return jsonify({"error": "Please enter a course name"}), 400
        
        # Get display name (optional)
        display_name = request.form.get('display_name')
        logger.info(f"Display name received: {display_name}")
        
        if not display_name:
            display_name = course_name  # Default to course name if not provided
            logger.info(f"Using course name as display name: {display_name}")
        
        # Get description (optional)
        description = request.form.get('description', '')
        logger.info(f"Description received: {description[:30]}..." if description else "No description")
        
        # Get character limit (optional, default 50,000)
        try:
            char_limit = int(request.form.get('char_limit', 50000))
            if char_limit < 50000:
                char_limit = 50000
            elif char_limit > 100000:
                char_limit = 100000
        except ValueError:
            char_limit = 50000
        
        # Check if files were uploaded
        files = request.files.getlist('files')
        if not files or not files[0]:
            logger.warning("No files part in the request")
            return jsonify({"error": "Please upload at least one file"}), 400
        
        logger.info(f"Files received: {[f.filename for f in files]}")
        
        # Save and extract text from each file
        combined_content = ""
        for file in files:
            filename = secure_filename(file.filename)
            file_ext = os.path.splitext(filename)[1].lower()
            temp_path = os.path.join('temp', filename)
            os.makedirs('temp', exist_ok=True)
            file.save(temp_path)
            logger.info(f"File saved temporarily at: {temp_path}")
            try:
                file_content = ""
                if file_ext == '.txt':
                    with open(temp_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                elif file_ext == '.pdf' and PYPDF2_AVAILABLE:
                    with open(temp_path, 'rb') as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        for page_num in range(len(pdf_reader.pages)):
                            page = pdf_reader.pages[page_num]
                            file_content += (page.extract_text() or "") + "\n"
                elif file_ext in ['.ppt', '.pptx'] and PPTX_AVAILABLE:
                    presentation = Presentation(temp_path)
                    for slide in presentation.slides:
                        for shape in slide.shapes:
                            if hasattr(shape, "text"):
                                file_content += shape.text + "\n"
                elif file_ext in ['.doc', '.docx'] and DOCX_AVAILABLE:
                    doc = docx.Document(temp_path)
                    for para in doc.paragraphs:
                        file_content += para.text + "\n"
                elif TEXTRACT_AVAILABLE:
                    file_content = textract.process(temp_path).decode('utf-8')
                else:
                    logger.warning(f"No library available to process {file_ext} files")
                    return jsonify({"error": f"The required libraries to process {file_ext} files are not installed. Supported: .txt, .pdf, .ppt, .pptx"}), 400
                
                # Clean the extracted content
                cleaned_content = clean_text(file_content)
                combined_content += cleaned_content + "\n\n"
                
            except Exception as e:
                logger.error(f"Error extracting content from {filename}: {str(e)}", exc_info=True)
                return jsonify({"error": f"Error extracting content from {filename}: {str(e)}"}), 500
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        
        if not combined_content.strip():
            logger.warning("Extracted content is empty")
            return jsonify({"error": "The extracted content is empty"}), 400
        
        # Check character limit
        content_length = len(combined_content)
        if content_length > char_limit:
            warning_message = f"Warning: Content exceeds {char_limit:,} characters (current: {content_length:,}). This will increase API costs. Each conversation will use approximately {content_length//4:,} tokens, costing about ${(content_length/4000)*0.001:.3f} per conversation."
            logger.warning(warning_message)
            return jsonify({
                "error": "Content too long",
                "warning": warning_message,
                "content_length": content_length,
                "char_limit": char_limit
            }), 400
        
        # Store content in database
        course_name_upper = course_name.upper()
        logger.info(f"Storing content for {course_name_upper} in database")
        try:
            db = get_db()
            ChatbotContent.create_or_update(
                db,
                code=course_name_upper,
                name=display_name,
                content=combined_content,
                description=description
            )
            chatbot = ChatbotContent.get_by_code(db, course_name_upper)
            if chatbot and not chatbot.is_active:
                chatbot.is_active = True
            db.commit()
            close_db(db)
            load_program_content()
            logger.info("Upload completed successfully")
            return jsonify({"success": True, "message": f"The {display_name} chatbot has been successfully updated"}), 200
        except Exception as e:
            if 'db' in locals():
                db.rollback()
                close_db(db)
            logger.error(f"Database error: {str(e)}", exc_info=True)
            return jsonify({"error": f"Database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# Update description route
@app.route('/admin_update_description', methods=['POST'])
@requires_auth
def admin_update_description():
    try:
        chatbot_name = request.form.get('chatbot_name')
        description = request.form.get('description', '')
        
        if not chatbot_name:
            return redirect(url_for('admin', 
                                    message='Chatbot name was not provided', 
                                    message_type='danger'))
        
        # Update description in the database
        chatbot_name_upper = chatbot_name.upper()
        db = get_db()
        try:
            chatbot = ChatbotContent.get_by_code(db, chatbot_name_upper)
            if not chatbot:
                return redirect(url_for('admin', 
                                        message=f'Chatbot {chatbot_name} not found in database', 
                                        message_type='danger'))
            
            chatbot.description = description
            db.commit()
            
            # Update memory cache
            program_descriptions[chatbot_name_upper] = description
            
            return redirect(url_for('admin', 
                                    message=f'Description for {chatbot.name} has been updated', 
                                    message_type='success'))
        finally:
            close_db(db)
    except Exception as e:
        return redirect(url_for('admin', 
                                message=f'An error occurred: {str(e)}', 
                                message_type='danger'))

# Delete chatbot route
@app.route('/admin_delete_chatbot', methods=['POST'])
@requires_auth
def admin_delete_chatbot():
    try:
        chatbot_name = request.form.get('chatbot_name')
        if not chatbot_name:
            return redirect(url_for('admin', 
                                    message='Chatbot name was not provided', 
                                    message_type='danger'))
        
        # Mark as inactive in database instead of deleting the file
        chatbot_name_upper = chatbot_name.upper()
        db = get_db()
        try:
            chatbot = ChatbotContent.get_by_code(db, chatbot_name_upper)
            if not chatbot:
                return redirect(url_for('admin', 
                                        message=f'Could not find {chatbot_name} chatbot in database', 
                                        message_type='danger'))
            
            # Mark as inactive
            chatbot.is_active = False
            db.commit()
            
            # Remove from program_content dictionary
            if chatbot_name_upper in program_content:
                del program_content[chatbot_name_upper]
            
            # Reload program content
            load_program_content()
            
            return redirect(url_for('admin', 
                                    message=f'The {chatbot.name} chatbot has been successfully deleted', 
                                    message_type='success'))
        finally:
            close_db(db)
        
    except Exception as e:
        return redirect(url_for('admin', 
                                message=f'An error occurred: {str(e)}', 
                                message_type='danger'))

# Restore chatbot route
@app.route('/admin_restore_chatbot', methods=['POST'])
@requires_auth
def admin_restore_chatbot():
    try:
        chatbot_name = request.form.get('chatbot_name')
        if not chatbot_name:
            return redirect(url_for('admin', 
                                    message='Chatbot name was not provided', 
                                    message_type='danger'))
        
        # Reactivate in database
        chatbot_name_upper = chatbot_name.upper()
        db = get_db()
        try:
            chatbot = ChatbotContent.get_by_code(db, chatbot_name_upper)
            if not chatbot:
                return redirect(url_for('admin', 
                                        message=f'Could not find {chatbot_name} chatbot in database', 
                                        message_type='danger'))
            
            # Mark as active
            chatbot.is_active = True
            db.commit()
            
            # Reload program content
            load_program_content()
            
            return redirect(url_for('admin', 
                                    message=f'The {chatbot.name} chatbot has been successfully restored', 
                                    message_type='success'))
        finally:
            close_db(db)
    except Exception as e:
        return redirect(url_for('admin', 
                                message=f'An error occurred: {str(e)}', 
                                message_type='danger'))

# Permanent delete chatbot route
@app.route('/admin_permanent_delete_chatbot', methods=['POST'])
@requires_auth
def admin_permanent_delete_chatbot():
    try:
        chatbot_name = request.form.get('chatbot_name')
        if not chatbot_name:
            return redirect(url_for('admin', 
                                    message='Chatbot name was not provided', 
                                    message_type='danger'))
        
        # Permanently delete from database
        chatbot_name_upper = chatbot_name.upper()
        db = get_db()
        try:
            chatbot = ChatbotContent.get_by_code(db, chatbot_name_upper)
            if not chatbot:
                return redirect(url_for('admin', 
                                        message=f'Could not find {chatbot_name} chatbot in database', 
                                        message_type='danger'))
            
            # Get display name before deletion for the success message
            display_name = chatbot.name
            
            # Permanently delete from database
            db.delete(chatbot)
            db.commit()
            
            # Reload program content
            load_program_content()
            
            return redirect(url_for('admin', 
                                    message=f'The {display_name} chatbot has been permanently deleted', 
                                    message_type='success'))
        finally:
            close_db(db)
    except Exception as e:
        return redirect(url_for('admin', 
                                message=f'An error occurred: {str(e)}', 
                                message_type='danger'))

# Route to get chatbot content
@app.route('/admin_get_chatbot_content/<chatbot_code>')
@requires_auth
def admin_get_chatbot_content(chatbot_code):
    db = get_db()
    try:
        chatbot = ChatbotContent.get_by_code(db, chatbot_code.upper())
        if chatbot and chatbot.is_active:
            return jsonify({
                "success": True, 
                "content": chatbot.content,
                "display_name": chatbot.name,
                "code": chatbot.code,
                "char_limit": chatbot.char_limit or 50000  # Add character limit
            })
        elif chatbot and not chatbot.is_active:
            return jsonify({"success": False, "error": "Chatbot is currently deleted (inactive). Restore it to view content."}), 404
        else:
            return jsonify({"success": False, "error": "Chatbot not found."}), 404
    except Exception as e:
        logger.error(f"Error fetching chatbot content for {chatbot_code}: {str(e)}")
        return jsonify({"success": False, "error": "Server error occurred."}), 500
    finally:
        close_db(db)

# Route to update chatbot content
@app.route('/admin_update_chatbot_content', methods=['POST'])
@requires_auth
def admin_update_chatbot_content():
    db = get_db()
    try:
        chatbot_code = request.form.get('chatbot_code')
        new_content = request.form.get('content')
        char_limit = int(request.form.get('char_limit', 50000))

        if not chatbot_code or new_content is None: # new_content can be empty string
            return jsonify({"success": False, "error": "Chatbot code and content are required."}), 400

        # Validate character limit
        if char_limit < 50000:
            char_limit = 50000
        elif char_limit > 100000:
            char_limit = 100000

        chatbot = ChatbotContent.get_by_code(db, chatbot_code.upper())
        if not chatbot:
            return jsonify({"success": False, "error": "Chatbot not found."}), 404
        
        if not chatbot.is_active:
            return jsonify({"success": False, "error": "Cannot update content of an inactive (deleted) chatbot. Please restore it first."}), 400

        # Check if files were uploaded
        files = request.files.getlist('files')
        if files and files[0]:
            combined_content = ""
            for file in files:
                filename = secure_filename(file.filename)
                file_ext = os.path.splitext(filename)[1].lower()
                temp_path = os.path.join('temp', filename)
                os.makedirs('temp', exist_ok=True)
                file.save(temp_path)
                try:
                    file_content = ""
                    if file_ext == '.txt':
                        with open(temp_path, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                    elif file_ext == '.pdf' and PYPDF2_AVAILABLE:
                        with open(temp_path, 'rb') as f:
                            pdf_reader = PyPDF2.PdfReader(f)
                            for page_num in range(len(pdf_reader.pages)):
                                page = pdf_reader.pages[page_num]
                                file_content += (page.extract_text() or "") + "\n"
                    elif file_ext in ['.ppt', '.pptx'] and PPTX_AVAILABLE:
                        presentation = Presentation(temp_path)
                        for slide in presentation.slides:
                            for shape in slide.shapes:
                                if hasattr(shape, "text"):
                                    file_content += shape.text + "\n"
                    elif file_ext in ['.doc', '.docx'] and DOCX_AVAILABLE:
                        doc = docx.Document(temp_path)
                        for para in doc.paragraphs:
                            file_content += para.text + "\n"
                    elif TEXTRACT_AVAILABLE:
                        file_content = textract.process(temp_path).decode('utf-8')
                    else:
                        return jsonify({"success": False, "error": f"The required libraries to process {file_ext} files are not installed. Supported: .txt, .pdf, .ppt, .pptx"}), 400
                    
                    # Clean the extracted content
                    cleaned_content = clean_text(file_content)
                    combined_content += cleaned_content + "\n\n"
                    
                except Exception as e:
                    logger.error(f"Error extracting content from {filename}: {str(e)}", exc_info=True)
                    return jsonify({"success": False, "error": f"Error extracting content from {filename}: {str(e)}"}), 500
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            
            if combined_content:
                new_content = combined_content

        # Check character limit
        content_length = len(new_content)
        if content_length > char_limit:
            warning_message = f"Warning: Content exceeds {char_limit:,} characters (current: {content_length:,}). This will increase API costs. Each conversation will use approximately {content_length//4:,} tokens, costing about ${(content_length/4000)*0.001:.3f} per conversation."
            return jsonify({
                "success": False,
                "error": "Content too long",
                "warning": warning_message,
                "content_length": content_length,
                "char_limit": char_limit
            }), 400

        chatbot.content = new_content
        chatbot.char_limit = char_limit  # Update character limit
        db.commit()
        
        # Reload content into memory
        load_program_content()
        
        logger.info(f"Content for chatbot {chatbot.name} (Code: {chatbot_code}) updated successfully.")
        return jsonify({
            "success": True, 
            "message": f"Content for {chatbot.name} updated successfully.",
            "display_name": chatbot.name 
        }), 200

    except Exception as e:
        if db:
            db.rollback()
        logger.error(f"Error updating chatbot content for {request.form.get('chatbot_code')}: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Server error occurred during content update."}), 500
    finally:
        if db:
            close_db(db)

# Route to update chatbot quota
@app.route('/admin_update_chatbot_quota', methods=['POST'])
@requires_auth
def admin_update_chatbot_quota():
    db = get_db()
    try:
        chatbot_code = request.form.get('chatbot_name') # Sent as 'chatbot_name' from admin.html
        quota_str = request.form.get('quota')

        if not chatbot_code or not quota_str:
            return jsonify({"success": False, "error": "Chatbot code and quota are required."}), 400
        
        try:
            quota = int(quota_str)
            if quota < 1:
                raise ValueError("Quota must be at least 1.")
        except ValueError as ve:
            return jsonify({"success": False, "error": str(ve)}), 400

        chatbot = ChatbotContent.get_by_code(db, chatbot_code.upper())
        if not chatbot:
            return jsonify({"success": False, "error": "Chatbot not found."}), 404
        
        chatbot.quota = quota
        db.commit()
        
        # Reload program content to update in-memory quota if you have such a cache
        # load_program_content() # Assuming this function would also update quotas in memory

        logger.info(f"Quota for chatbot {chatbot.name} (Code: {chatbot_code}) updated to {quota}.")
        return jsonify({
            "success": True, 
            "message": f"Quota for {chatbot.name} updated to {quota}.",
            "display_name": chatbot.name 
            }), 200

    except Exception as e:
        if db:
            db.rollback()
        logger.error(f"Error updating chatbot quota for {request.form.get('chatbot_name')}: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Server error occurred during quota update."}), 500
    finally:
        if db:
            close_db(db)

@app.route('/clear_chat_history', methods=['POST'])
@login_required
def clear_chat_history():
    user_id = session['user_id']
    program_code = session.get('current_program', 'BCC')
    db = get_db()
    try:
        # Hide all today's messages (set is_visible=False)
        today = datetime.datetime.utcnow().date()
        today_start = datetime.datetime.combine(today, datetime.time.min)
        today_end = datetime.datetime.combine(today, datetime.time.max)
        db.query(ChatHistory).filter(
            ChatHistory.user_id == user_id,
            ChatHistory.program_code == program_code,
            ChatHistory.timestamp >= today_start,
            ChatHistory.timestamp <= today_end,
            ChatHistory.is_visible == True
        ).update({ChatHistory.is_visible: False}, synchronize_session=False)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing chat history: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
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
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
