# ACS Chatbot Authentication System Implementation

## Overview

This document describes the complete implementation of a secure email + password authentication system for the ACS Chatbot application, replacing the previous last name + email system while maintaining full backward compatibility with existing CSV-based registration.

## 🔐 Security Features

### Password Security
- **Bcrypt Hashing**: All passwords are hashed using bcrypt with automatic salt generation
- **No Plain Text Storage**: Passwords are never stored in plain text - even administrators cannot view them
- **Minimum Requirements**: 8-character minimum password length
- **Secure Verification**: Constant-time password comparison to prevent timing attacks

### Token-Based Security
- **Secure Tokens**: Uses `itsdangerous` library for cryptographically signed tokens
- **Time-Limited**: Password reset tokens expire in 1 hour, setup tokens in 24 hours
- **Salt Protection**: Different salts for different token types (reset vs setup)

### Session Management
- **Flask-Login Integration**: Secure session management with remember-me functionality
- **Automatic Logout**: Sessions expire appropriately
- **CSRF Protection**: Built-in protection against cross-site request forgery

## 🔄 Registration Flow

### New User Registration (2-Step Process)

#### Step 1: Credential Verification
- User enters **Last Name** and **Email**
- System validates against existing CSV authorization data
- If authorized, registration data is stored in session for step 2

#### Step 2: Password Setup
- User sets up their password (minimum 8 characters)
- Password is hashed and stored securely
- Account is created with all CSV-derived permissions (LO Root IDs)
- User can immediately log in with email + password

### Existing User Handling
- **Users with passwords**: Redirected to login
- **Users without passwords**: Automatically sent password setup email

## 🔑 Login System

### Email + Password Authentication
- Users log in with **Email** and **Password** (no more last name required)
- Secure password verification using bcrypt
- Optional "Remember Me" functionality
- Automatic redirection to program selection

### Legacy Support
- Old login route redirects to new system
- Existing user data preserved
- CSV authorization system maintained

## 📧 Email-Based Password Management

### Password Reset Flow
1. User clicks "Forgot Password?" on login page
2. Enters email address
3. Receives secure reset link (1-hour expiration)
4. Sets new password via secure form
5. Can immediately log in with new password

### First-Time Setup Flow
1. Existing users (CSV or admin-added) click "First Time User?"
2. Enter last name and email for verification
3. Receive password setup email (24-hour expiration)
4. Set up password via secure form
5. Account activated for email + password login

### Admin-Added Users
- When admin adds a user, password setup email is automatically sent
- User receives welcome email with setup instructions
- 24-hour window to complete setup

## 🛠 Technical Implementation

### Database Changes
```sql
-- Added columns to users table
ALTER TABLE users ADD COLUMN email VARCHAR UNIQUE;
ALTER TABLE users ADD COLUMN password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN visit_count INTEGER DEFAULT 0;
```

### New Dependencies
```
flask-bcrypt==1.0.1      # Password hashing
flask-login==0.6.3       # Session management  
flask-mail==0.9.1        # Email functionality
itsdangerous==2.1.2      # Secure tokens
email-validator==2.1.0   # Email validation
```

### User Model Enhancements
```python
class User(UserMixin, Base):
    # ... existing fields ...
    password_hash = Column(String(255), nullable=True)
    
    def set_password(self, password):
        """Hash and store password securely"""
        
    def check_password(self, password):
        """Verify password against stored hash"""
        
    def has_password(self):
        """Check if user has a password set"""
        
    @classmethod
    def get_by_email(cls, db, email):
        """Find user by email address"""
```

### New Routes
- `/register` - Step 1: Credential verification
- `/register/password` - Step 2: Password setup
- `/login` - Email + password authentication
- `/forgot-password` - Password reset request
- `/reset-password/<token>` - Password reset form
- `/first-time-password` - First-time setup request
- `/setup-password/<token>` - Password setup form

### Email Templates
- **Password Reset**: Secure link with 1-hour expiration
- **Password Setup**: Welcome message with 24-hour setup window
- **Admin Added**: Notification for admin-added users

## 🔒 Security Considerations

### Password Storage
- Bcrypt hashing with automatic salt generation
- No reversible encryption - passwords cannot be recovered
- Secure random salt for each password

### Token Security
- Cryptographically signed tokens prevent tampering
- Time-limited expiration prevents replay attacks
- Different salts for different token types

### Email Security
- Secure token-based links
- No sensitive information in email content
- Clear expiration times communicated to users

### Session Security
- Flask-Login secure session management
- Proper logout functionality
- Remember-me with secure cookies

## 📋 Backward Compatibility

### Existing Data Preservation
- All existing user accounts preserved
- CSV authorization system maintained
- LO Root ID permissions unchanged
- Visit counts and other data intact

### Registration System
- CSV validation still required for new registrations
- Same authorization rules apply
- LO Root IDs automatically assigned from CSV data

### Admin Functions
- All existing admin functions work unchanged
- User management enhanced with password status
- CSV upload/download functionality preserved

## 🧪 Testing

### Automated Tests
- Password hashing and verification
- Database schema validation
- User model method testing
- Token generation and validation

### Manual Testing Checklist
- [ ] New user registration (2-step process)
- [ ] Email + password login
- [ ] Password reset flow
- [ ] First-time user setup
- [ ] Admin user addition with email
- [ ] CSV-based registration still works
- [ ] Existing users can set passwords
- [ ] Session management and logout

## 🚀 Deployment Notes

### Environment Variables Required
```bash
# Email configuration
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com

# Flask secret key (for sessions and tokens)
FLASK_SECRET_KEY=your-secure-secret-key
```

### Database Migration
```bash
# Run the database migration
python -m alembic upgrade head

# Or manually add columns if needed
python add_password_columns.py
```

### Package Installation
```bash
pip install -r requirements.txt
```

## 📈 Benefits

### For Users
- **Secure Authentication**: Industry-standard password security
- **Easy Password Recovery**: Self-service password reset
- **Better UX**: Single email field for login
- **Remember Me**: Convenient session persistence

### For Administrators
- **Enhanced Security**: No plain-text password storage
- **Automated Onboarding**: Automatic setup emails for new users
- **Audit Trail**: Better tracking of user authentication
- **Reduced Support**: Self-service password management

### For System
- **Scalability**: Standard authentication patterns
- **Maintainability**: Clean separation of concerns
- **Compliance**: Industry-standard security practices
- **Future-Proof**: Foundation for additional security features

## 🔮 Future Enhancements

### Potential Additions
- Two-factor authentication (2FA)
- Password complexity requirements
- Account lockout after failed attempts
- Password history to prevent reuse
- Single Sign-On (SSO) integration
- OAuth integration (Google, Microsoft)

### Monitoring & Analytics
- Login attempt tracking
- Password reset frequency monitoring
- User authentication patterns
- Security event logging

---

## 📞 Support

For technical issues or questions about the authentication system:

1. Check the application logs for detailed error messages
2. Verify email configuration for password reset functionality
3. Ensure database migrations have been applied
4. Test with the provided test script: `python test_auth_system.py`

The authentication system is designed to be robust and secure while maintaining the existing user experience and administrative capabilities. 