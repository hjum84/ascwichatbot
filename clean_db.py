from models import User, ChatbotContent, get_db, close_db, ChatHistory, UserLORootID, ChatbotLORootAssociation, Base, engine
from sqlalchemy import text

# Drop all tables with CASCADE
with engine.connect() as conn:
    conn.execute(text('DROP TABLE IF EXISTS users CASCADE'))
    conn.execute(text('DROP TABLE IF EXISTS chatbot_contents CASCADE'))
    conn.execute(text('DROP TABLE IF EXISTS chat_history CASCADE'))
    conn.execute(text('DROP TABLE IF EXISTS user_lo_root_ids CASCADE'))
    conn.execute(text('DROP TABLE IF EXISTS chatbot_lo_root_ids CASCADE'))
    conn.execute(text('DROP TABLE IF EXISTS lo_mappings CASCADE'))
    conn.execute(text('DROP TABLE IF EXISTS alembic_version CASCADE'))
    conn.commit()

# Recreate all tables
Base.metadata.create_all(bind=engine)

print("Database cleaned successfully") 