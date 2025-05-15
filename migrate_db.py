from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL")

def migrate():
    # Create engine
    engine = create_engine(DATABASE_URL)
    
    # Add char_limit column
    with engine.connect() as conn:
        try:
            # Add char_limit column if it doesn't exist
            conn.execute(text("""
                ALTER TABLE chatbot_contents 
                ADD COLUMN IF NOT EXISTS char_limit INTEGER DEFAULT 50000
            """))
            conn.commit()
            print("Successfully added char_limit column")
        except Exception as e:
            print(f"Error during migration: {str(e)}")
            conn.rollback()

if __name__ == "__main__":
    migrate() 