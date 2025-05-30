 Chatbot Essential Features Documentation

This document provides comprehensive technical information about the key features of the chatbot system, including user interface elements, mobile optimization, content formatting, data management, and backend functionality.

## Table of Contents

1. [Markdown Support](#markdown-support)
2. [Conversation Management](#conversation-management)
3. [Mobile Optimization](#mobile-optimization)
4. [User Interface Features](#user-interface-features)
5. [Backend Core Functionality](#backend-core-functionality)

## Markdown Support

The chatbot supports Markdown formatting in both user and bot messages, enabling richer text presentation.

### Implementation Details

- **Markdown Parser**: Uses the `marked.js` library for client-side Markdown parsing
- **HTML Sanitization**: Employs `DOMPurify` to prevent XSS attacks when rendering Markdown
- **Server-side Processing**: Uses `markdown2` library for server-side Markdown parsing

### Supported Markdown Elements

- **Basic Formatting**: Bold, italic, underline, strikethrough
- **Lists**: Ordered and unordered lists
- **Headers**: Multiple levels (H1-H6)
- **Code Blocks**: Both inline code and multi-line code blocks with syntax highlighting
- **Blockquotes**: For emphasizing quoted text
- **Tables**: Structured data display
- **Links**: Hyperlinks to external resources

### Markdown Rendering Process

```javascript
// Process the Markdown and apply it
const parsedContent = marked.parse(rawText);
element.innerHTML = typeof DOMPurify !== 'undefined' ? 
                  DOMPurify.sanitize(parsedContent) : 
                  parsedContent;
```

### Server-Side Implementation

```python
def parse_markdown(text):
    """Convert markdown text to HTML"""
    return markdown2.markdown(text)
```

## Conversation Management

The chatbot provides features for managing conversation history and deleting conversation data.

### Conversation Deletion

#### User-Level Deletion

Users can delete their conversation history with a specific chatbot:

1. **Deletion Button**: Located in the top-right corner of the chat interface
2. **Confirmation Dialog**: Prevents accidental deletion
3. **Soft Delete Implementation**: Marks conversations as hidden rather than permanently deleting

```javascript
document.getElementById('clear-history-btn').addEventListener('click', function() {
    if (confirm("Are you sure you want to delete this conversation history? This action cannot be undone.")) {
        fetch("{{ url_for('clear_chat_history') }}", {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ program: '{{ program }}'})
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                chatBox.innerHTML = '';
                // Re-add welcome message with Markdown processing
                const welcomeMessage = '{{ intro_message|safe }}';
                addMessage(welcomeMessage, 'bot system-welcome-message', true);
                alert("Conversation history cleared.");
            }
        });
    }
});
```

#### Admin-Level Deletion

Administrators have more granular control over conversation deletion:

1. **Mass Deletion**: Delete all conversations across the system
2. **Chatbot-Specific**: Delete all conversations for a specific chatbot
3. **User-Specific**: Delete all conversations for a specific user
4. **Permanent Deletion**: Records are completely removed from the database

### Database Implementation

```python
@app.route('/admin/delete_conversations', methods=['POST'])
@requires_auth
def admin_delete_conversations():
    """Delete conversations based on specified criteria"""
    delete_type = request.form.get('delete_type')
    
    if delete_type == 'all':
        # Delete all conversations from database
        db.query(ChatHistory).delete()
        db.commit()
        
    elif delete_type == 'by_chatbot':
        chatbot_code = request.form.get('chatbot_code')
        # Delete matching records
        db.query(ChatHistory).filter(ChatHistory.program_code == chatbot_code).delete()
        db.commit()
        
    elif delete_type == 'by_user':
        user_id = request.form.get('user_id')
        # Delete matching records
        db.query(ChatHistory).filter(ChatHistory.user_id == user_id).delete()
        db.commit()
```

## Mobile Optimization

The chatbot is optimized for mobile devices to ensure a seamless user experience across all platforms.

### Responsive Design

- **Viewport Configuration**: Meta tag ensures proper scaling on mobile devices
  ```html
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  ```

- **Mobile-Specific CSS**: Media queries for optimizing layout on small screens
  ```css
  @media (max-width: 767px) {
      .chat-container {
          width: 100%;
          height: 100vh;
          border-radius: 0;
          box-shadow: none;
      }
      
      .message {
          max-width: 90%;
          padding: 10px 14px;
      }
      
      textarea#userInput {
          font-size: 15px;
          max-height: 100px;
      }
  }
  ```

### Mobile Input Handling

- **Virtual Keyboard Management**: Handles viewport changes when keyboard appears
  ```javascript
  if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', () => {
          // Ensure the input is visible when keyboard appears
          inputContainer.scrollIntoView({ behavior: 'smooth', block: 'end' });
          scrollToBottom();
      });
  }
  ```

- **Auto-Resize Text Input**: Adjusts height based on content
- **Touch-Friendly Controls**: Larger touch targets for buttons
- **Soft Keyboard Integration**: Proper focus and input management

### Attachment Features

- **Native Mobile Integration**: Camera and microphone access
- **Compact UI Elements**: Space-efficient design for small screens
- **Touch-Optimized Buttons**: Easier to tap on mobile devices

## User Interface Features

The chatbot provides a rich, interactive user interface with various visual features.

### Message Styling

- **Message Bubbles**: Different styles for user and bot messages
- **Animation Effects**: Smooth fade-in for new messages
- **Typing Indicator**: Visual dots animation while waiting for bot response

```css
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

.message {
    animation: fadeIn 0.3s ease-out;
}
```

### Typing Animation

Bot responses appear with a realistic typing animation:

```javascript
function typeMessage(element, text, speed = 10) {
  return new Promise((resolve) => {
    let i = 0;
    element.classList.add('typing');
    function type() {
      if (i < text.length) {
        element.textContent += text.charAt(i);
        i++;
        setTimeout(type, speed);
        scrollToBottom();
      } else {
        element.classList.remove('typing');
        resolve();
      }
    }
    element.textContent = '';
    type();
  });
}
```

### Voice Input Features

- **Microphone Button**: Animated button for voice recording
- **Recording Indicator**: Visual feedback during recording
- **Wave Animation**: Pulsing animation effect while recording

```css
.mic-btn.active .mic-wave {
  opacity: 1;
  animation: mic-wave-pulse 1.2s infinite;
}

@keyframes mic-wave-pulse {
  0% { transform: translate(-50%, -50%) scale(1); opacity: 0.7; }
  70% { transform: translate(-50%, -50%) scale(1.4); opacity: 0.2; }
  100% { transform: translate(-50%, -50%) scale(1.7); opacity: 0; }
}
```

### Input Features

- **Auto-Expanding Textarea**: Grows with content
- **Send Button Animation**: Subtle scale effect on hover
- **Smooth Scrolling**: Automatically scrolls to show new messages

## Backend Core Functionality

The chatbot's backend implements several sophisticated features for performance and reliability.

### Caching System

- **LRU Cache**: Least Recently Used caching for API responses
- **Content Hashing**: Efficient content identification
- **Response Deduplication**: Prevents duplicate API calls

```python
@lru_cache(maxsize=1000)
def get_cached_response(content_hash, user_message):
    """Get cached response for the same content and user message."""
    # Find program code based on content hash
    program_code = None
    for code, hash_value in content_hashes.items():
        if hash_value == content_hash:
            program_code = code
            break
    
    # Get actual content to use in system message
    content = program_content[program_code]
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"You are an assistant..."},
            {"role": "user", "content": user_message}
        ],
        max_tokens=500
    )
    return response['choices'][0]['message']['content'].strip()
```

### Content Management

- **In-Memory Cache**: Fast access to chatbot content
- **Database Persistence**: Reliable storage in SQL database
- **Content Hashing**: Efficient identification and caching

```python
def load_program_content():
    # Clear existing content
    program_content.clear()
    program_names.clear()
    program_descriptions.clear()
    content_hashes.clear()
    
    # Get all active chatbot contents from database
    db = get_db()
    chatbots = db.query(ChatbotContent).filter(ChatbotContent.is_active == True).all()
    
    # Load content into memory
    for chatbot in chatbots:
        program_content[chatbot.code] = chatbot.content
        program_names[chatbot.code] = chatbot.name
        program_descriptions[chatbot.code] = chatbot.description or ""
        # Store content hash for caching
        content_hashes[chatbot.code] = get_content_hash(chatbot.content)
```

### Authentication and Security

- **Session Management**: User authentication and session tracking
- **CSRF Protection**: Prevents cross-site request forgery
- **Admin Authentication**: Separate authentication for administration

```python
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function
```

### Database Design

- **User Model**: Stores user information and preferences
- **ChatbotContent Model**: Stores chatbot configuration and knowledge base
- **ChatHistory Model**: Records conversation history with visibility control

```python
class ChatHistory(Base):
    __tablename__ = 'chat_history'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    program_code = Column(String, nullable=False, index=True)
    user_message = Column(Text, nullable=False)
    bot_message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    is_visible = Column(Boolean, nullable=False, default=True)
```

### API Integration

- **OpenAI Integration**: Communication with AI models
- **Error Handling**: Graceful handling of API failures
- **Rate Limiting**: Prevents excessive API usage

### Text Processing and Extraction

- **File Extraction**: Support for multiple file formats (PDF, DOCX, PPTX, TXT)
- **Text Summarization**: Intelligent content summarization
- **Content Cleaning**: Removes unnecessary formatting and noise

### System Monitoring

- **Database Monitoring**: Tracks database size and usage
- **Usage Statistics**: Records conversation counts and patterns
- **Performance Tracking**: Monitors system response times 