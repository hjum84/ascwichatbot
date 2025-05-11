from models import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text('DROP TABLE IF EXISTS chatbot_contents CASCADE;'))
    conn.commit()
print('chatbot_contents 테이블 삭제 완료') 