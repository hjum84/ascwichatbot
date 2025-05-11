from models import Base, engine
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
print('모든 테이블을 삭제 후 재생성 완료') 