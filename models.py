# models.py
import os
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from dotenv import load_dotenv
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

# User model
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    visit_count = Column(Integer, default=0)
    current_program = Column(String, default="BCC")
    
    @classmethod
    def get_by_credentials(cls, db, last_name, email):
        """Safely get user by credentials"""
        return db.query(cls).filter(
            cls.last_name == last_name,
            cls.email == email
        ).first()
    
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
            "visit_count": self.visit_count,
            "current_program": self.current_program
        }

# Chatbot content model
class ChatbotContent(Base):
    __tablename__ = 'chatbot_contents'
    
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)  # 예: "BCC", "MI"
    name = Column(String, nullable=False)  # 표시 이름
    description = Column(Text, nullable=True)  # 프로그램 설명
    content = Column(Text, nullable=False)  # 콘텐츠 요약 전체 내용
    is_active = Column(Boolean, default=True)  # 활성화 상태
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    @classmethod
    def get_by_code(cls, db, code):
        """Get chatbot content by code"""
        return db.query(cls).filter(cls.code == code).first()
    
    @classmethod
    def get_all_active(cls, db):
        """Get all active chatbot contents"""
        return db.query(cls).filter(cls.is_active == True).all()
    
    @classmethod
    def create_or_update(cls, db, code, name, content, description=None):
        """Create or update chatbot content"""
        existing = cls.get_by_code(db, code)
        if existing:
            existing.name = name
            existing.content = content
            if description is not None:
                existing.description = description
            existing.updated_at = datetime.datetime.utcnow()
            return existing
        else:
            new_content = cls(
                code=code,
                name=name,
                description=description,
                content=content
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
            "content": self.content,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

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
