from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL")

def check_and_clean():
    # Create engine
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            # Check for Housing Insecurity chatbot
            result = conn.execute(text("""
                SELECT * FROM chatbot_contents 
                WHERE code LIKE '%HOUSING%' OR name LIKE '%Housing%'
            """))
            
            rows = result.fetchall()
            print(f"Found {len(rows)} Housing Insecurity entries:")
            for row in rows:
                print(f"ID: {row[0]}, Code: {row[1]}, Name: {row[2]}, Active: {row[5]}")
            
            # Permanently delete Housing Insecurity chatbot
            conn.execute(text("""
                DELETE FROM chatbot_contents 
                WHERE code LIKE '%HOUSING%' OR name LIKE '%Housing%'
            """))
            conn.commit()
            print("\nPermanently deleted Housing Insecurity chatbot")
            
        except Exception as e:
            print(f"Error: {str(e)}")
            conn.rollback()

if __name__ == "__main__":
    check_and_clean() 