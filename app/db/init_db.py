from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.models.user import User
from app.models.job import Job

def clean_db():
    """Clean all tables in the database"""
    from app.db.session import engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def init_db():
    """Initialize the database"""
    from app.db.session import engine
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db() 