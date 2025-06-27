from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Enum, Index, Text
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
    company = Column(String(100), nullable=False)
    position = Column(String(100), nullable=False)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.DRAFT)
    applied_date = Column(DateTime)
    notes = Column(Text)  # Using Text for unlimited length
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with ResumeVersion
    resume_versions = relationship("ResumeVersion", back_populates="job", cascade="all, delete-orphan")
    # Order interview stages by scheduled_date
    interview_stages = relationship("InterviewStage", back_populates="job", 
                                 cascade="all, delete-orphan",
                                 order_by="InterviewStage.scheduled_date")

    def __repr__(self):
        try:
            company = self.company.scalar() if not self.company.is_(None) else ''
            position = self.position.scalar() if not self.position.is_(None) else ''
            status = self.status.scalar().value if not self.status.is_(None) else 'Unknown'
            return f"<Job(company='{company}', position='{position}', status='{status}')>"
        except Exception:
            return "<Job(error rendering repr)>"

class ResumeVersion(Base):
    __tablename__ = 'resume_versions'

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    s3_key = Column(String(255), nullable=False, unique=True)
    job_id = Column(Integer, ForeignKey('jobs.id'), nullable=False)
    upload_date = Column(DateTime, default=datetime.utcnow)
    version = Column(Integer, nullable=False)
    notes = Column(Text)

    # Relationship with Job
    job = relationship("Job", back_populates="resume_versions")

    # Index for faster lookups
    __table_args__ = (
        Index('idx_resume_job_id', 'job_id'),
    )

    def __repr__(self):
        try:
            filename = self.filename.scalar() if not self.filename.is_(None) else ''
            version = self.version.scalar() if not self.version.is_(None) else 0
            job_id = self.job_id.scalar() if not self.job_id.is_(None) else 0
            return f"<ResumeVersion(filename='{filename}', version={version}, job_id={job_id})>"
        except Exception:
            return "<ResumeVersion(error rendering repr)>"

class InterviewStage(Base):
    __tablename__ = 'interview_stages'

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'), nullable=False)
    stage_type = Column(Enum(InterviewStageType), nullable=False)
    custom_stage_name = Column(String(100))  # Used when stage_type is CUSTOM
    status = Column(Enum(InterviewStageStatus), default=InterviewStageStatus.UPCOMING)
    scheduled_date = Column(DateTime)
    completed_date = Column(DateTime)
    key_takeaway = Column(Text)
    general_notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with Job
    job = relationship("Job", back_populates="interview_stages")
    # Relationship with InterviewQuestion
    questions = relationship("InterviewQuestion", back_populates="stage", 
                           cascade="all, delete-orphan",
                           order_by="InterviewQuestion.created_at")

    # Index for faster lookups
    __table_args__ = (
        Index('idx_interview_job_id', 'job_id'),
    )

    def __repr__(self):
        try:
            job_id = self.job_id.scalar() if not self.job_id.is_(None) else 0
            stage_name = (self.custom_stage_name.scalar() 
                         if not self.stage_type.is_(None) and self.stage_type.scalar() == InterviewStageType.CUSTOM 
                         else self.stage_type.scalar().value if not self.stage_type.is_(None) 
                         else 'Unknown')
            status = self.status.scalar().value if not self.status.is_(None) else 'Unknown'
            return f"<InterviewStage(job_id={job_id}, stage='{stage_name}', status='{status}')>"
        except Exception:
            return "<InterviewStage(error rendering repr)>"

    @property
    def is_upcoming(self):
        try:
            return not self.status.is_(None) and self.status.scalar() == InterviewStageStatus.UPCOMING
        except Exception:
            return False

    @property
    def is_current(self):
        try:
            return not self.status.is_(None) and self.status.scalar() == InterviewStageStatus.CURRENT
        except Exception:
            return False

    @property
    def is_completed(self):
        try:
            return not self.status.is_(None) and self.status.scalar() == InterviewStageStatus.COMPLETED
        except Exception:
            return False

class InterviewQuestion(Base):
    __tablename__ = 'interview_questions'

    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey('interview_stages.id'), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with InterviewStage
    stage = relationship("InterviewStage", back_populates="questions")

    # Index for faster lookups
    __table_args__ = (
        Index('idx_question_stage_id', 'stage_id'),
    )

    def __repr__(self):
        try:
            stage_id = self.stage_id.scalar() if not self.stage_id.is_(None) else 0
            if self.question.is_(None):
                return f"<InterviewQuestion(stage_id={stage_id}, question='')>"
            question = self.question.scalar()
            preview = question[:30] + '...' if len(question) > 30 else question
            return f"<InterviewQuestion(stage_id={stage_id}, question='{preview}')>"
        except Exception:
            return "<InterviewQuestion(error rendering repr)>"

def init_db(db_url='sqlite:///jobs.db'):
    """Initialize the database and create all tables"""
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return engine 