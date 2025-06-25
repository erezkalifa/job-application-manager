from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

class ApplicationStatus(enum.Enum):
    DRAFT = "Draft"
    APPLIED = "Applied"
    INTERVIEWING = "Interviewing"
    OFFER = "Offer"
    REJECTED = "Rejected"
    WITHDRAWN = "Withdrawn"

class Job(Base):
    __tablename__ = 'jobs'

    id = Column(Integer, primary_key=True)
    company = Column(String, nullable=False)
    position = Column(String, nullable=False)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.DRAFT)
    applied_date = Column(DateTime)
    notes = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with ResumeVersion
    resume_versions = relationship("ResumeVersion", back_populates="job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Job(company='{self.company}', position='{self.position}', status='{self.status}')>"

class ResumeVersion(Base):
    __tablename__ = 'resume_versions'

    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    s3_key = Column(String, nullable=False)
    job_id = Column(Integer, ForeignKey('jobs.id'), nullable=False)
    upload_date = Column(DateTime, default=datetime.utcnow)
    version = Column(Integer, nullable=False)
    notes = Column(String)

    # Relationship with Job
    job = relationship("Job", back_populates="resume_versions")

    def __repr__(self):
        return f"<ResumeVersion(filename='{self.filename}', version={self.version}, job_id={self.job_id})>"

def init_db(db_url='sqlite:///jobs.db'):
    """Initialize the database and create all tables"""
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return engine 