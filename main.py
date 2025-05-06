import openai
import os
import datetime
import smartsheet
import csv
import io
import threading
import logging
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, redirect, url_for, make_response, Response, session
from functools import wraps
import re
from models import User, get_db, close_db

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialize Flask application
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")  # Add a secret key for session management

# Program content dictionaries
program_content = {}
program_names = {
    "BCC": "Building Coaching Competency",
    "MI": "Motivational Interviewing",
    "Safety": "Safety and Risk Assessment"
}

# Load content summaries for each program
def load_program_content():
    # BCC content
    try:
        with open("content_summary_bcc.txt", "r", encoding="utf-8") as f:
            program_content["BCC"] = f.read()
    except FileNotFoundError:
        program_content["BCC"] = "BCC content not available"
    
    # MI content
    try:
        with open("content_summary_mi.txt", "r", encoding="utf-8") as f:
            program_content["MI"] = f.read()
    except FileNotFoundError:
        program_content["MI"] = "MI content not available"
    
    # Safety content
    try:
        with open("content_summary_safety.txt", "r", encoding="utf-8") as f:
            program_content["Safety"] = f.read()
    except FileNotFoundError:
        program_content["Safety"] = "Safety content not available"

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
                return "User not found. Please register first.", 400
                
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
def program_select():
    # Verify user is logged in
    if 'user_id' not in session:
        logger.warning("User not in session, redirecting to login")
        return redirect(url_for('login'))
        
    # Enable all programs - previously these were conditionally enabled
    mi_enabled = True
    safety_enabled = True
    
    logger.debug("Program select page for user: %s", session.get('user_id'))
    return render_template('program_select.html', 
                         mi_enabled=mi_enabled,
                         safety_enabled=safety_enabled)

# Set program route
@app.route('/set_program/<program>')
def set_program(program):
    # Verify valid program
    if program not in ["BCC", "MI", "Safety"]:
        return redirect(url_for('program_select'))
    
    # Verify user is logged in
    if 'user_id' not in session:
        logger.warning("User not in session, redirecting to login")
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    logger.debug("Setting program %s for user %s", program, user_id)
    
    # Get DB session
    db = get_db()
    try:
        # Get user by ID
        user = User.get_by_id(db, user_id)
        
        if not user:
            logger.warning("User not found in database")
            close_db(db)
            # Clear session and redirect to login
            session.clear()
            return redirect(url_for('login'))
            
        # Update program
        user.current_program = program
        db.commit()
        
        # Set in session
        session['current_program'] = program
        
        # Cleanup
        close_db(db)
        
        # Redirect to the appropriate program page
        if program == "BCC":
            return redirect(url_for('index_bcc'))
        elif program == "MI":
            return redirect(url_for('index_mi'))
        elif program == "Safety":
            return redirect(url_for('index_safety'))
        else:
            return redirect(url_for('program_select'))
        
    except Exception as e:
        # Rollback on error
        db.rollback()
        close_db(db)
        logger.error("Error setting program: %s", str(e))
        return redirect(url_for('program_select'))

# BCC Chatbot interface
@app.route('/index_bcc')
def index_bcc():
    # Verify user is logged in
    if 'user_id' not in session:
        logger.warning("User not logged in, redirecting to login")
        return redirect(url_for('login'))
        
    # Set current program to BCC
    session['current_program'] = 'BCC'
    
    logger.debug("Loading BCC chatbot interface")
    return render_template('index.html',
                         program='BCC',
                         program_display_name=program_names.get('BCC', "Building Coaching Competency"))

# MI Chatbot interface
@app.route('/index_mi')
def index_mi():
    # Verify user is logged in
    if 'user_id' not in session:
        logger.warning("User not logged in, redirecting to login")
        return redirect(url_for('login'))
        
    # Set current program to MI
    session['current_program'] = 'MI'
    
    logger.debug("Loading MI chatbot interface")
    return render_template('index.html',
                         program='MI',
                         program_display_name=program_names.get('MI', "Motivational Interviewing"))

# Safety Chatbot interface
@app.route('/index_safety')
def index_safety():
    # Verify user is logged in
    if 'user_id' not in session:
        logger.warning("User not logged in, redirecting to login")
        return redirect(url_for('login'))
        
    # Set current program to Safety
    session['current_program'] = 'Safety'
    
    logger.debug("Loading Safety chatbot interface")
    return render_template('index.html',
                         program='Safety',
                         program_display_name=program_names.get('Safety', "Safety and Risk Assessment"))

# Legacy index route - redirect to program selection
@app.route('/index')
def index():
    # If somehow users reach this route, redirect to program selection
    logger.debug("Redirecting from legacy index route to program selection")
    return redirect(url_for('program_select'))

# Chat endpoint for processing user messages
@app.route('/chat', methods=['POST'])
def chat():
    # Verify user is logged in
    if 'user_id' not in session:
        logger.warning("User not logged in, redirecting to login")
        return jsonify({"reply": "Session expired. Please log in again."}), 401

    user_message = request.json.get("message")
    if not user_message:
        return jsonify({"error": "A question is required."}), 400

    # Get the current program from session
    current_program = session.get('current_program', 'BCC')
    logger.debug(f"Processing chat for program: {current_program}")
    
    # Get content for the selected program
    content = program_content.get(current_program, "Content not available for this program")

    # Check quota using cookie
    quota = request.cookies.get('chat_quota')
    if quota:
        quota = int(quota)
    else:
        quota = 0

    if quota >= 300:
        return jsonify({"reply": "You have used all your quota for today."}), 200

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

        # Record conversation in Smartsheet asynchronously
        def record_smartsheet_async(user_question, chatbot_reply, program):
            try:
                # Also record which program was being used
                record_in_smartsheet(f"[{program}] {user_question}", chatbot_reply)
            except Exception as smex:
                logger.error("Error recording in Smartsheet: %s", str(smex))

        threading.Thread(target=record_smartsheet_async, args=(user_message, chatbot_reply, current_program)).start()

        # Create the response object and update the chat quota cookie
        response_obj = make_response(jsonify({"reply": chatbot_reply}))
        quota += 1
        expires = datetime.datetime.now() + datetime.timedelta(days=1)
        response_obj.set_cookie('chat_quota', str(quota), expires=expires)

        return response_obj

    except Exception as e:
        logger.error("Chat error: %s", str(e))
        return jsonify({"error": str(e)}), 500

# Program switch route
@app.route('/switch_program')
def switch_program():
    return redirect(url_for('program_select'))

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
    return render_template('export.html')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
