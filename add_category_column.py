# Script to add category column to chatbot_contents table
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
print("DATABASE_URL =", DATABASE_URL)

# Connect to the database
conn = psycopg2.connect(DATABASE_URL)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cursor = conn.cursor()

try:
    # Check if column already exists
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'chatbot_contents' AND column_name = 'category'")
    if cursor.fetchone() is None:
        # Add the new column with default value 'standard'
        print("Adding category column to chatbot_contents table...")
        cursor.execute("ALTER TABLE chatbot_contents ADD COLUMN category VARCHAR(50) NOT NULL DEFAULT 'standard'")
        print("Column added successfully!")
    else:
        print("Column 'category' already exists in the chatbot_contents table.")

except Exception as e:
    print(f"Error: {e}")
finally:
    cursor.close()
    conn.close()

print("Migration completed.") 