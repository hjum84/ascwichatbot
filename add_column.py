import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get the database URL from your environment
DATABASE_URL = os.getenv("DATABASE_URL")

def add_current_program_column():
    """Add the current_program column to the users table if it doesn't exist."""
    try:
        # Connect to the database
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if the column already exists
        cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='users' AND column_name='current_program'
        """)
        
        if cursor.fetchone() is None:
            print("Adding 'current_program' column to the users table...")
            # Add the column with a default value of 'BCC'
            cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN current_program VARCHAR DEFAULT 'BCC'
            """)
            conn.commit()
            print("Column added successfully.")
        else:
            print("The 'current_program' column already exists in the users table.")
        
        # Close the connection
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return False
        
    return True

if __name__ == "__main__":
    add_current_program_column() 