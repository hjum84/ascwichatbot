import os
from sqlalchemy import create_engine, inspect, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable is not set.")
    exit()

engine = create_engine(DATABASE_URL)
inspector = inspect(engine)

def get_table_schema(table_name):
    print(f"\n--- Schema for table: {table_name} ---")
    try:
        if inspector.has_table(table_name):
            columns = inspector.get_columns(table_name)
            if columns:
                for column in columns:
                    print(f"  Column: {column['name']}, Type: {column['type']}")
            else:
                print(f"  Table '{table_name}' has no columns or inspector couldn't retrieve them.")
            
            # Check foreign keys
            fks = inspector.get_foreign_keys(table_name)
            if fks:
                print(f"  Foreign Keys for {table_name}:")
                for fk in fks:
                    print(f"    - Constrained columns: {fk['constrained_columns']}")
                    print(f"      Referred table: {fk['referred_table']}")
                    print(f"      Referred columns: {fk['referred_columns']}")
            else:
                print(f"  No foreign keys found for {table_name}.")

            # Check primary key
            pk_constraint = inspector.get_pk_constraint(table_name)
            if pk_constraint and pk_constraint['constrained_columns']:
                print(f"  Primary Key for {table_name}: {pk_constraint['constrained_columns']}")
            else:
                print(f"  No primary key found or defined for {table_name}.")

        else:
            print(f"  Table '{table_name}' does not exist.")
    except Exception as e:
        print(f"  Error inspecting table {table_name}: {e}")

if __name__ == "__main__":
    tables_to_inspect = [
        "users", 
        "chatbot_contents", 
        "user_lo_root_ids", 
        "chatbot_lo_root_association",
        "alembic_version" # Also check the alembic version table
    ]
    
    with engine.connect() as connection:
        print("Successfully connected to the database.")
        for table in tables_to_inspect:
            get_table_schema(table)
        
        # Get current Alembic revision from the database
        try:
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            current_revision = result.scalar_one_or_none()
            if current_revision:
                print(f"\n--- Current Alembic revision in DB: {current_revision} ---")
            else:
                print("\n--- Alembic version table exists but is empty or version_num not found. ---")
        except Exception as e:
            # This might happen if alembic_version table doesn't exist or has a different structure
            if "relation \"alembic_version\" does not exist" in str(e).lower():
                 print("\n--- alembic_version table does not exist. ---")
            else:
                print(f"\n--- Error querying alembic_version table: {e} ---")

    print("\nSchema inspection complete.") 