# models.py
import os
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session, relationship
from sqlalchemy.sql import func
from dotenv import load_dotenv
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
load_dotenv()

# Get the database URL from your Render environment
DATABASE_URL = os.getenv("DATABASE_URL")
print("DATABASE_URL =", DATABASE_URL)

# Create an engine with proper connection handling 
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    pool_recycle=1800,  # 30 minutes
    pool_size=10,
    max_overflow=20,
    echo=False  # Set to True for SQL debugging
)

# Create scoped session to ensure thread safety
session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SessionLocal = scoped_session(session_factory)

# Base class for models
Base = declarative_base()
Base.query = SessionLocal.query_property()

# Association table for User and LORootID (Many-to-Many)
class UserLORootID(Base):
    __tablename__ = "user_lo_root_ids"
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    lo_root_id = Column(String, primary_key=True)

# User model
class User(UserMixin, Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=True)  # New: for password authentication
    visit_count = Column(Integer, default=0)
    status = Column(String, default="Inactive", nullable=False)  # Active/Inactive
    date_added = Column(DateTime, default=datetime.datetime.utcnow)
    expiry_date = Column(DateTime) # Calculated as date_added + 2 years

    # Relationship to handle multiple lo_root_ids
    lo_root_ids = relationship("UserLORootID", backref="user")

    def set_password(self, password):
        """Hash and set password using pbkdf2:sha256 (compatible with Render)"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        """Check if provided password matches hash with backward compatibility"""
        if not self.password_hash:
            return False
        
        # Check if this is an old scrypt hash that needs conversion
        if self.password_hash.startswith('scrypt:'):
            try:
                # Try to verify with Werkzeug (might fail on Render)
                is_valid = check_password_hash(self.password_hash, password)
                if is_valid:
                    # Auto-upgrade to pbkdf2:sha256 for future compatibility
                    self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
                    return True
                return False
            except ValueError as e:
                if 'unsupported hash type scrypt' in str(e):
                    # Cannot verify scrypt hash on this platform
                    # User will need to reset password
                    return False
                raise e
        else:
            # Standard verification for pbkdf2 and other supported methods
            return check_password_hash(self.password_hash, password)
    
    def has_password(self):
        """Check if user has a password set"""
        return self.password_hash is not None

    @classmethod
    def get_by_credentials(cls, db, last_name, email):
        """Safely get user by credentials"""
        return db.query(cls).filter(
            cls.last_name == last_name,
            cls.email == email
        ).first()
    
    @classmethod
    def get_by_email(cls, db, email):
        """Safely get user by email"""
        return db.query(cls).filter(cls.email == email).first()
    
    @classmethod
    def get_by_id(cls, db, user_id):
        """Safely get user by ID"""
        return db.query(cls).filter(cls.id == user_id).first()
    
    def to_dict(self):
        """Convert user object to dictionary"""
        return {
            "id": self.id,
            "last_name": self.last_name,
            "email": self.email,
            "has_password": self.has_password(),
            "visit_count": self.visit_count,
            "status": self.status,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "lo_root_ids": [ulr.lo_root_id for ulr in self.lo_root_ids]
        }

    @classmethod
    def delete_all_users(cls, db):
        """Delete all users and their associated lo_root_ids"""
        try:
            # First delete all associated lo_root_ids
            db.query(UserLORootID).delete()
            # Then delete all users
            db.query(cls).delete()
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e

    @classmethod
    def delete_user(cls, db, user_id):
        """Delete a specific user and their associated lo_root_ids"""
        try:
            # First delete associated lo_root_ids
            db.query(UserLORootID).filter(UserLORootID.user_id == user_id).delete()
            # Then delete the user
            user = db.query(cls).filter(cls.id == user_id).first()
            if user:
                db.delete(user)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            raise e

# Association table for ChatbotContent and LORootID (Many-to-Many)
class ChatbotLORootAssociation(Base):
    __tablename__ = 'chatbot_lo_root_association'
    chatbot_id = Column(Integer, ForeignKey('chatbot_contents.id'), primary_key=True)
    lo_root_id = Column(String, primary_key=True)

# Chatbot content model
class ChatbotContent(Base):
    __tablename__ = 'chatbot_contents'
    
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)  # 예: "BCC", "MI"
    name = Column(String(100), nullable=False)  # 표시 이름
    description = Column(Text, nullable=True)  # 프로그램 설명
    content = Column(Text, nullable=False)  # 콘텐츠 요약 전체 내용
    is_active = Column(Boolean, default=True)  # 활성화 상태
    char_limit = Column(Integer, default=50000)  # Add character limit field
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    quota = Column(Integer, nullable=False, default=3)  # Max questions quota
    intro_message = Column(Text, nullable=False, default="Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day.")  # Customizable intro message
    category = Column(String(50), nullable=False, default="standard")  # Program category: standard, tap, elearning
    system_prompt_role = Column(Text, nullable=True)  # System prompt: Role section
    system_prompt_guidelines = Column(Text, nullable=True)  # System prompt: Important Guidelines section
    auto_delete_days = Column(Integer, nullable=True, default=None)  # Auto-delete conversations after N days (NULL = never delete)

    # Relationship to handle multiple lo_root_ids
    lo_root_ids = relationship("ChatbotLORootAssociation", backref="chatbot")

    def should_auto_delete(self):
        """Check if auto-delete is enabled for this chatbot"""
        return self.auto_delete_days is not None and self.auto_delete_days > 0
    
    def get_auto_delete_text(self):
        """Get human-readable text for auto-delete setting (for UI display)"""
        if not self.should_auto_delete():
            return "Keep conversations (never delete)"
        return f"Auto-delete after {self.auto_delete_days} days"

    @classmethod
    def get_by_code(cls, db, code):
        """Get chatbot content by code (case-insensitive search).
        Assumes the 'code' parameter is already uppercased by the caller."""
        return db.query(cls).filter(func.upper(cls.code) == func.upper(code)).first()
    
    @classmethod
    def get_all_active(cls, db):
        """Get all active chatbot contents"""
        return db.query(cls).filter(cls.is_active == True).all()
    
    @classmethod
    def create_or_update(cls, db, code, name, content, description=None, quota=3, 
                        intro_message="Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day.",
                        char_limit=50000, is_active=True, category="standard",
                        system_prompt_role=None, system_prompt_guidelines=None,
                        auto_delete_days=None):  # 👈 NEW: Auto-delete setting (maintains backward compatibility)
        """Create or update chatbot content"""
        existing = cls.get_by_code(db, code)
        if existing:
            existing.name = name
            existing.content = content
            if description is not None:
                existing.description = description
            existing.quota = quota
            existing.intro_message = intro_message
            existing.char_limit = char_limit
            existing.is_active = is_active
            existing.category = category
            existing.updated_at = datetime.datetime.utcnow()
            if system_prompt_role is not None:
                existing.system_prompt_role = system_prompt_role
            if system_prompt_guidelines is not None:
                existing.system_prompt_guidelines = system_prompt_guidelines
            # 👈 NEW: Only update auto_delete_days if explicitly provided
            if auto_delete_days is not None:
                existing.auto_delete_days = auto_delete_days
            return existing
        else:
            new_content = cls(
                code=code,
                name=name,
                description=description,
                content=content,
                quota=quota,
                intro_message=intro_message,
                char_limit=char_limit,
                is_active=is_active,
                category=category,
                system_prompt_role=system_prompt_role,
                system_prompt_guidelines=system_prompt_guidelines,
                auto_delete_days=auto_delete_days  # 👈 NEW: Auto-delete setting for new chatbots
                # lo_root_ids will be handled separately after creation/update
            )
            db.add(new_content)
            return new_content
    
    def to_dict(self):
        """Convert chatbot content to dictionary"""
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "intro_message": self.intro_message,
            "category": self.category,
            "system_prompt_role": self.system_prompt_role,
            "system_prompt_guidelines": self.system_prompt_guidelines,
            "auto_delete_days": self.auto_delete_days,  # 👈 NEW: Include auto-delete setting
            "auto_delete_text": self.get_auto_delete_text(),  # 👈 NEW: Human-readable text
            "lo_root_ids": [assoc.lo_root_id for assoc in self.lo_root_ids]
        }

# Chat history model
class ChatHistory(Base):
    __tablename__ = 'chat_history'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    program_code = Column(String, nullable=False, index=True)
    user_message = Column(Text, nullable=False)
    bot_message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    is_visible = Column(Boolean, nullable=False, default=True)  # For UI hiding
    deletion_notified_at = Column(DateTime, nullable=True, default=None)  # 👈 NEW: Track when deletion notification was sent
    
    def is_eligible_for_deletion(self, chatbot):
        """Check if this conversation is eligible for auto-deletion"""
        if not chatbot.should_auto_delete():
            return False
        
        cutoff_date = datetime.datetime.utcnow() - timedelta(days=chatbot.auto_delete_days)
        return self.timestamp < cutoff_date
    
    def needs_deletion_notification(self, chatbot):
        """Check if this conversation needs a deletion warning notification (3 days before deletion)"""
        if not chatbot.should_auto_delete():
            return False
        
        if self.deletion_notified_at:  # Already notified
            return False
            
        # Calculate warning date (3 days before deletion)
        warning_days = max(3, chatbot.auto_delete_days // 10)  # At least 3 days, or 10% of retention period
        warning_date = datetime.datetime.utcnow() - timedelta(days=chatbot.auto_delete_days - warning_days)
        return self.timestamp < warning_date

# Create database tables
Base.metadata.create_all(bind=engine)

# Database session management
def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Will be closed by the caller

def close_db(db):
    """Safely close database session"""
    if db is not None:
        db.close()
