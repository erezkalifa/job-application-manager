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

class InterviewStageStatus(enum.Enum):
    UPCOMING = "Upcoming"
    CURRENT = "Current"
    COMPLETED = "Completed"

class InterviewStageType(enum.Enum):
    PHONE_SCREEN = "Phone Screen"
    HR_INTERVIEW = "HR Interview"
    TECHNICAL_INTERVIEW = "Technical Interview"
    SYSTEM_DESIGN = "System Design"
    BEHAVIORAL = "Behavioral Interview"
    CODING_CHALLENGE = "Coding Challenge"
    TAKE_HOME = "Take Home Assignment"
    ONSITE = "Onsite Interview"
    FINAL_ROUND = "Final Round"
    TEAM_MEETING = "Team Meeting"
    CUSTOM = "Custom"

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
    interview_stages = relationship("InterviewStage", back_populates="job", cascade="all, delete-orphan")

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

class InterviewStage(Base):
    __tablename__ = 'interview_stages'

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'), nullable=False)
    stage_type = Column(Enum(InterviewStageType), nullable=False)
    custom_stage_name = Column(String)  # Used when stage_type is CUSTOM
    status = Column(Enum(InterviewStageStatus), default=InterviewStageStatus.UPCOMING)
    scheduled_date = Column(DateTime)
    completed_date = Column(DateTime)
    key_takeaway = Column(String)
    general_notes = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with Job
    job = relationship("Job", back_populates="interview_stages")
    # Relationship with InterviewQuestion
    questions = relationship("InterviewQuestion", back_populates="stage", cascade="all, delete-orphan")

    def __repr__(self):
        stage_name = self.custom_stage_name if self.stage_type == InterviewStageType.CUSTOM else self.stage_type.value
        return f"<InterviewStage(job_id={self.job_id}, stage='{stage_name}', status='{self.status.value}')>"

class InterviewQuestion(Base):
    __tablename__ = 'interview_questions'

    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey('interview_stages.id'), nullable=False)
    question = Column(String, nullable=False)
    answer = Column(String)
    notes = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with InterviewStage
    stage = relationship("InterviewStage", back_populates="questions")

    def __repr__(self):
        return f"<InterviewQuestion(stage_id={self.stage_id}, question='{self.question[:30]}...'>"

def init_db(db_url='sqlite:///jobs.db'):
    """Initialize the database and create all tables"""
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return engine 