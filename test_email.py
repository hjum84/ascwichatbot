#!/usr/bin/env python3
"""
Test script to debug email sending functionality
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_gmail_connection():
    """Test Gmail SMTP connection and email sending"""
    
    # Get email settings from .env
    mail_server = os.getenv('MAIL_SERVER')
    mail_port = int(os.getenv('MAIL_PORT', 587))
    mail_username = os.getenv('MAIL_USERNAME')
    mail_password = os.getenv('MAIL_PASSWORD')
    
    print("🧪 Testing Gmail SMTP Connection")
    print("=" * 50)
    print(f"MAIL_SERVER: {mail_server}")
    print(f"MAIL_PORT: {mail_port}")
    print(f"MAIL_USERNAME: {mail_username}")
    print(f"MAIL_PASSWORD: {'*' * len(mail_password) if mail_password else 'None'}")
    print()
    
    if not all([mail_server, mail_port, mail_username, mail_password]):
        print("❌ Missing email configuration in .env file")
        return False
    
    try:
        print("🔄 Step 1: Creating SMTP connection...")
        server = smtplib.SMTP(mail_server, mail_port)
        
        print("🔄 Step 2: Starting TLS encryption...")
        server.starttls()
        
        print("🔄 Step 3: Attempting login...")
        server.login(mail_username, mail_password)
        
        print("✅ SMTP connection successful!")
        
        # Test email sending
        print("🔄 Step 4: Sending test email...")
        
        # Create test email
        msg = MIMEMultipart()
        msg['From'] = mail_username
        msg['To'] = "hyunjoon.um@acs.nyc.gov"  # Your email for testing
        msg['Subject'] = "ACS Chatbot - Email Test"
        
        body = """
        This is a test email from the ACS Chatbot authentication system.
        
        If you receive this email, the email configuration is working correctly!
        
        Test Details:
        - Sender: ascwichatbot2025@gmail.com
        - Time: Just now
        - Purpose: Testing SMTP connection
        
        Best regards,
        ACS Chatbot System
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server.sendmail(mail_username, "hyunjoon.um@acs.nyc.gov", msg.as_string())
        
        print("✅ Test email sent successfully!")
        print(f"   Check your inbox: hyunjoon.um@acs.nyc.gov")
        
        server.quit()
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ Authentication Error: {e}")
        print("💡 Possible solutions:")
        print("   1. Enable 'Less secure app access' in Gmail")
        print("   2. Use App Password instead of regular password")
        print("   3. Enable 2-step verification and create App Password")
        return False
        
    except smtplib.SMTPException as e:
        print(f"❌ SMTP Error: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        return False

def show_gmail_setup_instructions():
    """Show instructions for setting up Gmail"""
    print("\n" + "=" * 60)
    print("📧 Gmail Setup Instructions")
    print("=" * 60)
    print("Option 1: App Password (Recommended)")
    print("-" * 40)
    print("1. Go to Gmail → Google Account → Security")
    print("2. Enable 2-Step Verification")
    print("3. Go to App passwords")
    print("4. Select 'Mail' and 'Other (Custom name)'")
    print("5. Enter 'ACS Chatbot' as the name")
    print("6. Copy the 16-character password")
    print("7. Replace MAIL_PASSWORD in .env with this password")
    print()
    print("Option 2: Less Secure Apps (Not Recommended)")
    print("-" * 40)
    print("1. Go to Gmail → Google Account → Security")
    print("2. Turn ON 'Less secure app access'")
    print("3. Keep using current password")

if __name__ == "__main__":
    success = test_gmail_connection()
    
    if not success:
        show_gmail_setup_instructions()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Email system is working correctly!")
    else:
        print("⚠️  Email system needs configuration.") 