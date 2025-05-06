# Multi-Program Learning Chatbot

A chatbot application for NYC Child Welfare and Juvenile Justice staff that provides assistance with different learning programs:

1. **Building Coaching Competency (BCC)** - Learn about coaching skills, mindset, and processes
2. **Motivational Interviewing (MI)** - Learn about motivational interviewing techniques and approaches (coming soon)
3. **Safety and Risk Assessment** - Learn about safety planning and risk assessment in child welfare (coming soon)

## Features

- User registration and login system
- Program selection interface
- Chatbot interaction based on the selected learning program
- Admin interface for user management and data export
- Integration with Smartsheet for storing conversation history

## Getting Started

### Prerequisites

- Python 3.7+
- PostgreSQL database
- OpenAI API key

### Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Configure environment variables (see ENV Configuration section)
4. Run database migrations
5. Start the application:
   ```
   python main.py
   ```

## ENV Configuration

Create a `.env` file with the following variables:

```
# OpenAI API
OPENAI_API_KEY=your_openai_api_key_here

# Database
DATABASE_URL=postgresql://username:password@host:port/database

# Admin Auth
AUTH_USERNAME=admin
AUTH_PASSWORD=password

# Smartsheet Integration (Optional)
SMARTSHEET_ACCESS_TOKEN=your_smartsheet_token_here
SMARTSHEET_SHEET_ID=your_sheet_id_here
SMARTSHEET_TIMESTAMP_COLUMN=column_id_for_timestamp
SMARTSHEET_QUESTION_COLUMN=column_id_for_question
SMARTSHEET_RESPONSE_COLUMN=column_id_for_response

# Program Enablement (true/false)
ENABLE_MI=false
ENABLE_SAFETY=false

# Flask
FLASK_SECRET_KEY=your_random_secret_key_here
```

## Adding Content for Learning Programs

Each learning program has its own content summary file:

- `content_summary_bcc.txt` - Building Coaching Competency content
- `content_summary_mi.txt` - Motivational Interviewing content
- `content_summary_safety.txt` - Safety and Risk Assessment content

To update the content for a program, edit the corresponding file.

## Enabling Programs

By default, only the BCC program is enabled. To enable additional programs, set the corresponding environment variables to `true`:

```
ENABLE_MI=true
ENABLE_SAFETY=true
```

## Admin Access

To access the admin interface, go to:
- `/users` - View registered users
- `/export` - Export user data
- `/delete_registration` - Remove user registrations

Use the admin credentials configured in the `.env` file to log in. 