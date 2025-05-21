import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the database URL from your environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable not set.")
    exit(1)

def add_is_visible_column():
    print(f"Connecting to database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}") # Basic obfuscation for logs
    engine = None
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as connection:
            # Check if the column already exists
            inspector_query = text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='chat_history' AND column_name='is_visible'"
            )
            result = connection.execute(inspector_query)
            column_exists = result.fetchone()

            if column_exists:
                print("Column 'is_visible' already exists in 'chat_history'. No action taken.")
            else:
                print("Column 'is_visible' does not exist. Adding it now...")
                # Add the is_visible column, nullable=False, default=True
                # For PostgreSQL:
                alter_query_pg = text(
                    "ALTER TABLE chat_history ADD COLUMN is_visible BOOLEAN NOT NULL DEFAULT TRUE"
                )
                # For SQLite (syntax is slightly different, though Render uses Postgres):
                # alter_query_sqlite = text(
                #     "ALTER TABLE chat_history ADD COLUMN is_visible BOOLEAN NOT NULL DEFAULT 1"
                # )
                
                # Assuming PostgreSQL for Render
                connection.execute(alter_query_pg)
                connection.commit()
                print("Successfully added 'is_visible' column to 'chat_history' table with NOT NULL constraint and default value TRUE.")
            
            # Verify by setting existing NULLs to True (if any somehow existed, though unlikely with NOT NULL)
            # This step is more for safety if the column was somehow added without a default before
            # or if existing rows predate the default.
            # With NOT NULL DEFAULT TRUE, new rows are fine, and this handles old rows if they became NULL.
            # However, if the column was just added with NOT NULL DEFAULT TRUE, all rows should have it.
            # For safety, we can ensure all existing rows have `is_visible` set to True if they were somehow missed.
            # This is generally not needed if the ALTER TABLE command includes the DEFAULT for all existing rows.
            # check_and_update_nulls_query = text(
            #     "UPDATE chat_history SET is_visible = TRUE WHERE is_visible IS NULL"
            # )
            # result = connection.execute(check_and_update_nulls_query)
            # connection.commit()
            # print(f"Ensured all existing rows have 'is_visible' set (updated {result.rowcount} rows).")


    except Exception as e:
        print(f"An error occurred: {e}")
        if engine:
            engine.dispose() # Ensure engine is disposed on error
        return False
    finally:
        if engine:
            engine.dispose()
    return True

if __name__ == "__main__":
    if add_is_visible_column():
        print("Migration script completed successfully.")
    else:
        print("Migration script failed.") 