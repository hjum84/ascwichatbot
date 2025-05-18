# add_intro_message.py
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def add_intro_message_to_chatbot_contents():
    """Add the intro_message column to chatbot_contents table if it doesn't exist"""
    default_intro = "Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day."
    
    # Get the database URL from environment
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    # Create a direct engine connection
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Check if column exists using information schema
        result = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chatbot_contents' AND column_name='intro_message')"
        ))
        column_exists = result.scalar()
        
        if column_exists:
            print("Column 'intro_message' already exists in chatbot_contents table.")
            # Update existing records with default intro message if they have NULL values
            conn.execute(
                text("UPDATE chatbot_contents SET intro_message = :default_intro WHERE intro_message IS NULL"),
                {"default_intro": default_intro}
            )
            conn.commit()
            print("Updated NULL intro_message values with default message.")
        else:
            print("Column doesn't exist, adding it...")
            # Add column
            conn.execute(text("ALTER TABLE chatbot_contents ADD COLUMN intro_message TEXT"))
            # Set default value for all existing records
            conn.execute(
                text("UPDATE chatbot_contents SET intro_message = :default_intro"),
                {"default_intro": default_intro}
            )
            conn.commit()
            print("Column 'intro_message' successfully added to chatbot_contents table.")

if __name__ == "__main__":
    add_intro_message_to_chatbot_contents() 