from sqlalchemy import Column, Integer, String, DateTime, Text, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
import enum
from datetime import datetime

class JobStatus(str, enum.Enum):
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    PENDING = "pending"

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    company = Column(String(100), nullable=False)
    position = Column(String(100), nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING)
    resume_path = Column(String(255), nullable=True)  # Path to the resume in storage
    notes = Column(Text, nullable=True)
    applied_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship with ResumeVersion
    resumes = relationship("ResumeVersion", back_populates="job", cascade="all, delete-orphan")

class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(255), nullable=False, unique=True)  # Path to the resume in storage
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    version = Column(Integer, nullable=False)
    upload_date = Column(DateTime(timezone=True), default=datetime.utcnow)
    notes = Column(Text, nullable=True)

    # Relationship with Job
    job = relationship("Job", back_populates="resumes") 