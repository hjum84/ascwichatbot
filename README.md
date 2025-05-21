# Multi-Program Learning Chatbot

A chatbot application for NYC Child Welfare and Juvenile Justice staff that provides assistance with different learning programs:

1. **Building Coaching Competency (BCC)** - Learn about coaching skills, mindset, and processes
2. **Motivational Interviewing (MI)** - Learn about motivational interviewing techniques and approaches
3. **Safety and Risk Assessment** - Learn about safety planning and risk assessment in child welfare

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

# ASCWI Chatbot System

An AI-powered chatbot system for the Association for Supervisors in Child Welfare Institute (ASCWI), designed to answer questions about various training programs.

## Functionality Preservation Guidelines

### IMPORTANT: Ensuring Existing Functionality Is Not Lost

When making code changes to this system, it's critical to ensure that existing functionality is not inadvertently disabled or removed. Follow these guidelines to prevent regression:

#### Before Making Changes:

1. **Document Current Behavior**: Thoroughly understand the current functionality before modifying it.
   - Test all relevant features and document their behavior
   - Take note of edge cases that are currently handled correctly

2. **Understand Dependencies**: Recognize how components interact before changing them.
   - Identify which parts of the code depend on the component you're modifying
   - Note any shared resources or global variables affected by your changes

#### During Implementation:

3. **Incremental Changes**: Make small, focused changes rather than large rewrites.
   - Test each incremental change before moving to the next one
   - Commit changes in logical units with clear descriptions

4. **Preserve Functionality First, Optimize Later**: When fixing a bug or adding a feature, first make sure existing functionality works, then optimize.
   - Add new functionality alongside existing code before removing the old code
   - Use feature flags to control enabling/disabling new functionality during testing

5. **Comment Temporary Changes**: Clearly mark temporary modifications.
   - Add "TODO" comments to note incomplete implementations
   - Document any workarounds that will need to be revisited

#### Testing Requirements:

6. **Comprehensive Testing**: Test all affected features, not just the changed functionality.
   - Test on different browsers and devices if relevant
   - Test with various input types, especially file uploads with different formats/sizes

7. **Verify Multi-File Uploads**: Specifically ensure that multi-file upload functionality continues to work.
   - Test uploading various combinations of file types (txt, pdf, docx, pptx)
   - Verify that files are properly processed and combined
   - Check that PowerPoint files are processed correctly on both local and deployed environments

8. **Test Edge Cases**: Make sure your changes don't break existing edge case handling.
   - Test with empty files or invalid input
   - Test with very large files or extremely long content
   - Test with special characters or unusual formatting

#### After Implementation:

9. **Document Changes**: Update documentation to reflect your changes.
   - Note any changes to behavior, API, or interface
   - Explain new functionality and how it integrates with existing systems

10. **Monitor After Deployment**: Watch for unexpected issues after deployment.
    - Check logs for errors or warnings
    - Monitor performance metrics to ensure your changes don't negatively impact system performance

### Additional Guidelines for Specific Components

#### File Processing:

- The system processes multiple files and combines their content
- Maintain support for all currently supported file types: txt, pdf, docx, pptx
- Preserve temporary file management for PowerPoint files
- Maintain error handling for file processing failures

#### User Interface:

- Maintain all existing interaction patterns unless explicitly redesigning
- Preserve accessibility features
- Keep consistent error messaging and feedback

Remember that lost functionality is often more frustrating to users than delayed features. Always prioritize preserving existing capabilities when making changes.

## Installation

[Installation instructions...]

## Usage

[Usage instructions...]

## Configuration

[Configuration details...] 