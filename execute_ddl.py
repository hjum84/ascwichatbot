import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable is not set.")
    exit()

engine = create_engine(DATABASE_URL)

# DDL statements to execute
# Note: Using DO $$ ... END $$; for conditional DDL in PostgreSQL
ddl_statements = """
-- Users Table Adjustments

-- Drop columns that are not in the final User model or have different names/purposes
ALTER TABLE users DROP COLUMN IF EXISTS \"User_Status\";
ALTER TABLE users DROP COLUMN IF EXISTS \"lo_root_id\"; 
ALTER TABLE users DROP COLUMN IF EXISTS \"is_active\";
ALTER TABLE users DROP COLUMN IF EXISTS \"Registration_Date\";
ALTER TABLE users DROP COLUMN IF EXISTS \"Expiration_Date\";
ALTER TABLE users DROP COLUMN IF EXISTS \"is_admin\";
ALTER TABLE users DROP COLUMN IF EXISTS current_program;

-- Add new columns as defined in models.py
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='status') THEN
        ALTER TABLE users ADD COLUMN status VARCHAR(255) DEFAULT 'Inactive' NOT NULL;
    ELSE
        ALTER TABLE users ALTER COLUMN status TYPE VARCHAR(255),
                          ALTER COLUMN status SET DEFAULT 'Inactive',
                          ALTER COLUMN status SET NOT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='date_added') THEN
        ALTER TABLE users ADD COLUMN date_added TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL;
    ELSE
        ALTER TABLE users ALTER COLUMN date_added TYPE TIMESTAMP WITHOUT TIME ZONE,
                          ALTER COLUMN date_added SET DEFAULT CURRENT_TIMESTAMP,
                          ALTER COLUMN date_added SET NOT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='expiry_date') THEN
        ALTER TABLE users ADD COLUMN expiry_date TIMESTAMP WITHOUT TIME ZONE;
    ELSE
        ALTER TABLE users ALTER COLUMN expiry_date TYPE TIMESTAMP WITHOUT TIME ZONE;
    END IF;
END $$;

-- ChatbotContents Table Adjustments
ALTER TABLE chatbot_contents DROP COLUMN IF EXISTS lo_root_ids;
"""

if __name__ == "__main__":
    with engine.connect() as connection:
        try:
            connection.execute(text(ddl_statements))
            connection.commit() # Commit changes
            print("DDL statements executed successfully.")
        except Exception as e:
            connection.rollback() # Rollback on error
            print(f"Error executing DDL: {e}")
    print("DDL execution script finished.") 