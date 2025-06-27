from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import Engine, Column, or_
import logging
from datetime import datetime
from typing import Optional, List, Any, Generator, TypeVar, cast
from models import Job, ResumeVersion, ApplicationStatus, InterviewStage, InterviewQuestion, InterviewStageStatus, InterviewStageType
from contextlib import contextmanager

logger = logging.getLogger(__name__)

T = TypeVar('T')

class StorageManager:
    def __init__(self, engine: Engine) -> None:
        """Initialize the storage manager with a database engine"""
        Session = sessionmaker(bind=engine)
        self.Session = Session

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations."""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database error: {str(e)}")
            raise
        finally:
            session.close()

    def _validate_job_exists(self, session: Session, job_id: int) -> Job:
        """Validate that a job exists"""
        job = session.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job with ID {job_id} does not exist")
        return job

    def _validate_stage_exists(self, session: Session, stage_id: int) -> InterviewStage:
        """Validate that an interview stage exists"""
        stage = session.query(InterviewStage).filter_by(id=stage_id).first()
        if not stage:
            raise ValueError(f"Interview stage with ID {stage_id} does not exist")
        return stage

    def _validate_stage_data(self, stage_type: InterviewStageType, custom_stage_name: Optional[str]) -> None:
        """Validate interview stage data"""
        if stage_type == InterviewStageType.CUSTOM and not custom_stage_name:
            raise ValueError("Custom stage name is required for custom stage type")
        if stage_type != InterviewStageType.CUSTOM and custom_stage_name:
            raise ValueError("Custom stage name should only be set for custom stage type")

    def get_all_jobs(self) -> List[dict]:
        """Get all jobs from the database"""
        with self.session_scope() as session:
            jobs = session.query(Job).order_by(Job.updated_at.desc()).all()
            return [{
                'id': job.id,
                'company': job.company,
                'position': job.position,
                'status': job.status,
                'applied_date': job.applied_date if job.applied_date is not None else None,
                'notes': job.notes if job.notes is not None else None,
                'resume_versions': len(job.resume_versions)
            } for job in jobs]

    def get_job(self, job_id: int) -> Optional[dict]:
        """Get a specific job by ID"""
        with self.session_scope() as session:
            job = session.query(Job).filter_by(id=job_id).first()
            if not job:
                return None
            return {
                'id': job.id,
                'company': job.company,
                'position': job.position,
                'status': job.status,
                'applied_date': job.applied_date if job.applied_date is not None else None,
                'notes': job.notes if job.notes is not None else None,
                'resume_versions': [{
                    'id': version.id,
                    'filename': version.filename,
                    's3_key': version.s3_key,
                    'version': version.version,
                    'upload_date': version.upload_date,
                    'notes': version.notes if version.notes is not None else None
                } for version in job.resume_versions]
            }

    def _sync_initial_stage(self, session: Session, job_id: int, status: ApplicationStatus) -> None:
        """Sync the initial stage with the job status"""
        # Map job status to stage type and status
        status_to_stage = {
            ApplicationStatus.DRAFT: (InterviewStageType.PHONE_SCREEN, InterviewStageStatus.UPCOMING),
            ApplicationStatus.APPLIED: (InterviewStageType.PHONE_SCREEN, InterviewStageStatus.COMPLETED),
            ApplicationStatus.INTERVIEWING: (InterviewStageType.TECHNICAL_INTERVIEW, InterviewStageStatus.CURRENT),
            ApplicationStatus.OFFER: (InterviewStageType.FINAL_ROUND, InterviewStageStatus.COMPLETED),
            ApplicationStatus.REJECTED: (InterviewStageType.PHONE_SCREEN, InterviewStageStatus.COMPLETED),
            ApplicationStatus.WITHDRAWN: (InterviewStageType.PHONE_SCREEN, InterviewStageStatus.COMPLETED)
        }

        # Get the first stage if exists
        first_stage = session.query(InterviewStage).filter_by(job_id=job_id).order_by(InterviewStage.id.asc()).first()
        stage_type, stage_status = status_to_stage[status]

        current_time = datetime.now()
        
        if first_stage is not None:
            # Update existing first stage
            setattr(first_stage, 'stage_type', stage_type)
            setattr(first_stage, 'status', stage_status)
            if status == ApplicationStatus.APPLIED:
                setattr(first_stage, 'completed_date', current_time)
        else:
            # Create new first stage
            first_stage = InterviewStage()
            setattr(first_stage, 'job_id', job_id)
            setattr(first_stage, 'stage_type', stage_type)
            setattr(first_stage, 'status', stage_status)
            if status == ApplicationStatus.APPLIED:
                setattr(first_stage, 'completed_date', current_time)
            session.add(first_stage)

    def create_job(self, company: str, position: str, status: ApplicationStatus, 
                  applied_date: Optional[datetime] = None, notes: Optional[str] = None) -> dict:
        """Create a new job"""
        with self.session_scope() as session:
            # Create the job
            job = Job()
            setattr(job, 'company', company)
            setattr(job, 'position', position)
            setattr(job, 'status', status)
            setattr(job, 'applied_date', applied_date)
            setattr(job, 'notes', notes)
            session.add(job)
            session.flush()

            # Get the job ID as an integer
            job_id = session.query(Job.id).filter_by(
                company=company,
                position=position,
                status=status
            ).scalar()

            # Create initial stage
            self._sync_initial_stage(session, job_id, status)
            
            return {
                'id': job.id,
                'company': job.company,
                'position': job.position,
                'status': job.status,
                'applied_date': job.applied_date if job.applied_date is not None else None,
                'notes': job.notes if job.notes is not None else None,
                'resume_versions': []
            }

    def update_job(self, job_id: int, company: str, position: str, status: ApplicationStatus,
                  applied_date: Optional[datetime] = None, notes: Optional[str] = None) -> dict:
        """Update an existing job"""
        with self.session_scope() as session:
            job = self._validate_job_exists(session, job_id)
            setattr(job, 'company', company)
            setattr(job, 'position', position)
            setattr(job, 'status', status)
            setattr(job, 'applied_date', applied_date)
            setattr(job, 'notes', notes)

            # Sync initial stage with new status
            self._sync_initial_stage(session, job_id, status)

            return {
                'id': job.id,
                'company': job.company,
                'position': job.position,
                'status': job.status,
                'applied_date': job.applied_date if job.applied_date is not None else None,
                'notes': job.notes if job.notes is not None else None,
                'resume_versions': [{
                    'id': version.id,
                    'filename': version.filename,
                    's3_key': version.s3_key,
                    'version': version.version,
                    'upload_date': version.upload_date,
                    'notes': version.notes if version.notes is not None else None
                } for version in job.resume_versions]
            }

    def delete_job(self, job_id: int) -> None:
        """Delete a job"""
        with self.session_scope() as session:
            job = self._validate_job_exists(session, job_id)
            session.delete(job)

    def get_resume_versions(self, job_id: int) -> List[dict]:
        """Get all resume versions for a specific job"""
        with self.session_scope() as session:
            self._validate_job_exists(session, job_id)
            versions = session.query(ResumeVersion).filter_by(job_id=job_id).order_by(ResumeVersion.version.desc()).all()
            return [{
                'id': version.id,
                'filename': version.filename,
                's3_key': version.s3_key,
                'job_id': version.job_id,
                'version': version.version,
                'upload_date': version.upload_date,
                'notes': version.notes if version.notes is not None else None
            } for version in versions]

    def create_resume_version(self, job_id: int, filename: str, s3_key: str, 
                            version: int, notes: Optional[str] = None) -> dict:
        """Create a new resume version"""
        with self.session_scope() as session:
            self._validate_job_exists(session, job_id)
            resume = ResumeVersion()
            setattr(resume, 'job_id', job_id)
            setattr(resume, 'filename', filename)
            setattr(resume, 's3_key', s3_key)
            setattr(resume, 'version', version)
            setattr(resume, 'notes', notes)
            session.add(resume)
            session.flush()
            return {
                'id': resume.id,
                'filename': resume.filename,
                's3_key': resume.s3_key,
                'job_id': resume.job_id,
                'version': resume.version,
                'upload_date': resume.upload_date,
                'notes': resume.notes if resume.notes is not None else None
            }

    def get_resume_version(self, version_id: int) -> Optional[dict]:
        """Get a specific resume version by ID"""
        with self.session_scope() as session:
            version = session.query(ResumeVersion).filter_by(id=version_id).first()
            if not version:
                return None
            return {
                'id': version.id,
                'filename': version.filename,
                's3_key': version.s3_key,
                'job_id': version.job_id,
                'version': version.version,
                'upload_date': version.upload_date,
                'notes': version.notes if version.notes is not None else None
            }

    def delete_resume_version(self, version_id: int) -> None:
        """Delete a resume version"""
        with self.session_scope() as session:
            version = session.query(ResumeVersion).filter_by(id=version_id).first()
            if version:
                session.delete(version)

    def get_interview_stages(self, job_id: int) -> List[dict]:
        """Get all interview stages for a specific job"""
        with self.session_scope() as session:
            self._validate_job_exists(session, job_id)
            stages = session.query(InterviewStage).filter_by(job_id=job_id).order_by(InterviewStage.scheduled_date.asc()).all()
            return [{
                'id': stage.id,
                'stage_type': stage.stage_type,
                'custom_stage_name': stage.custom_stage_name if stage.custom_stage_name is not None else None,
                'status': stage.status,
                'scheduled_date': stage.scheduled_date if stage.scheduled_date is not None else None,
                'completed_date': stage.completed_date if stage.completed_date is not None else None,
                'key_takeaway': stage.key_takeaway if stage.key_takeaway is not None else None,
                'general_notes': stage.general_notes if stage.general_notes is not None else None,
                'questions': [{
                    'id': q.id,
                    'question': q.question if q.question is not None else None,
                    'answer': q.answer if q.answer is not None else None,
                    'notes': q.notes if q.notes is not None else None
                } for q in stage.questions]
            } for stage in stages]

    def create_interview_stage(self, job_id: int, stage_type: InterviewStageType, 
                             custom_stage_name: Optional[str] = None,
                             scheduled_date: Optional[datetime] = None, 
                             status: InterviewStageStatus = InterviewStageStatus.UPCOMING,
                             key_takeaway: Optional[str] = None, 
                             general_notes: Optional[str] = None) -> dict:
        """Create a new interview stage"""
        with self.session_scope() as session:
            self._validate_job_exists(session, job_id)
            self._validate_stage_data(stage_type, custom_stage_name)
            
            stage = InterviewStage()
            setattr(stage, 'job_id', job_id)
            setattr(stage, 'stage_type', stage_type)
            setattr(stage, 'custom_stage_name', custom_stage_name)
            setattr(stage, 'scheduled_date', scheduled_date)
            setattr(stage, 'status', status)
            setattr(stage, 'key_takeaway', key_takeaway)
            setattr(stage, 'general_notes', general_notes)
            session.add(stage)
            session.flush()
            return {
                'id': stage.id,
                'job_id': stage.job_id,
                'stage_type': stage.stage_type,
                'custom_stage_name': stage.custom_stage_name if stage.custom_stage_name is not None else None,
                'status': stage.status,
                'scheduled_date': stage.scheduled_date if stage.scheduled_date is not None else None,
                'completed_date': stage.completed_date if stage.completed_date is not None else None,
                'key_takeaway': stage.key_takeaway if stage.key_takeaway is not None else None,
                'general_notes': stage.general_notes if stage.general_notes is not None else None,
                'questions': []
            }

    def get_interview_stage(self, stage_id: int) -> Optional[dict]:
        """Get a specific interview stage by ID"""
        with self.session_scope() as session:
            stage = self._validate_stage_exists(session, stage_id)
            if not stage:
                return None
            return {
                'id': stage.id,
                'job_id': stage.job_id,
                'stage_type': stage.stage_type,
                'custom_stage_name': stage.custom_stage_name if stage.custom_stage_name is not None else None,
                'status': stage.status,
                'scheduled_date': stage.scheduled_date if stage.scheduled_date is not None else None,
                'completed_date': stage.completed_date if stage.completed_date is not None else None,
                'key_takeaway': stage.key_takeaway if stage.key_takeaway is not None else None,
                'general_notes': stage.general_notes if stage.general_notes is not None else None,
                'questions': [{
                    'id': q.id,
                    'question': q.question if q.question is not None else None,
                    'answer': q.answer if q.answer is not None else None,
                    'notes': q.notes if q.notes is not None else None
                } for q in stage.questions]
            }

    def update_interview_stage(self, stage_id: int, stage_type: Optional[InterviewStageType] = None,
                             custom_stage_name: Optional[str] = None,
                             scheduled_date: Optional[datetime] = None,
                             completed_date: Optional[datetime] = None,
                             status: Optional[InterviewStageStatus] = None,
                             key_takeaway: Optional[str] = None,
                             general_notes: Optional[str] = None) -> dict:
        """Update an existing interview stage"""
        with self.session_scope() as session:
            stage = self._validate_stage_exists(session, stage_id)
            
            if stage_type is not None:
                self._validate_stage_data(stage_type, 
                                       custom_stage_name if custom_stage_name is not None 
                                       else cast(Optional[str], stage.custom_stage_name))
                setattr(stage, 'stage_type', stage_type)
            if custom_stage_name is not None:
                self._validate_stage_data(cast(InterviewStageType, stage.stage_type), custom_stage_name)
                setattr(stage, 'custom_stage_name', custom_stage_name)
            if scheduled_date is not None:
                setattr(stage, 'scheduled_date', scheduled_date)
            if completed_date is not None:
                setattr(stage, 'completed_date', completed_date)
            if status is not None:
                setattr(stage, 'status', status)
            if key_takeaway is not None:
                setattr(stage, 'key_takeaway', key_takeaway)
            if general_notes is not None:
                setattr(stage, 'general_notes', general_notes)
            return {
                'id': stage.id,
                'job_id': stage.job_id,
                'stage_type': stage.stage_type,
                'custom_stage_name': stage.custom_stage_name if stage.custom_stage_name is not None else None,
                'status': stage.status,
                'scheduled_date': stage.scheduled_date if stage.scheduled_date is not None else None,
                'completed_date': stage.completed_date if stage.completed_date is not None else None,
                'key_takeaway': stage.key_takeaway if stage.key_takeaway is not None else None,
                'general_notes': stage.general_notes if stage.general_notes is not None else None,
                'questions': [{
                    'id': q.id,
                    'question': q.question if q.question is not None else None,
                    'answer': q.answer if q.answer is not None else None,
                    'notes': q.notes if q.notes is not None else None
                } for q in stage.questions]
            }

    def delete_interview_stage(self, stage_id: int) -> None:
        """Delete an interview stage"""
        with self.session_scope() as session:
            stage = self._validate_stage_exists(session, stage_id)
            session.delete(stage)

    def get_interview_questions(self, stage_id: int) -> List[InterviewQuestion]:
        """Get all questions for a specific interview stage"""
        with self.session_scope() as session:
            self._validate_stage_exists(session, stage_id)
            return session.query(InterviewQuestion).filter_by(stage_id=stage_id).order_by(InterviewQuestion.created_at.asc()).all()

    def create_interview_question(self, stage_id: int, question: str, 
                                answer: Optional[str] = None, 
                                notes: Optional[str] = None) -> InterviewQuestion:
        """Create a new interview question"""
        with self.session_scope() as session:
            self._validate_stage_exists(session, stage_id)
            q = InterviewQuestion()
            setattr(q, 'stage_id', stage_id)
            setattr(q, 'question', question)
            setattr(q, 'answer', answer)
            setattr(q, 'notes', notes)
            session.add(q)
            session.flush()
            return q

    def get_interview_question(self, question_id: int) -> Optional[dict]:
        """Get a specific interview question by ID"""
        with self.session_scope() as session:
            question = session.query(InterviewQuestion).filter_by(id=question_id).first()
            if not question:
                return None
            return {
                'id': question.id,
                'question': question.question if question.question is not None else None,
                'answer': question.answer if question.answer is not None else None,
                'notes': question.notes if question.notes is not None else None,
                'stage': {
                    'id': question.stage.id,
                    'job_id': question.stage.job_id
                }
            }

    def update_interview_question(self, question_id: int, question: Optional[str] = None, 
                                answer: Optional[str] = None, 
                                notes: Optional[str] = None) -> InterviewQuestion:
        """Update an existing interview question"""
        with self.session_scope() as session:
            q = session.query(InterviewQuestion).filter_by(id=question_id).first()
            if not q:
                raise ValueError(f"Interview question with ID {question_id} does not exist")
            
            if question is not None:
                setattr(q, 'question', question)
            if answer is not None:
                setattr(q, 'answer', answer)
            if notes is not None:
                setattr(q, 'notes', notes)
            return q

    def delete_interview_question(self, question_id: int) -> None:
        """Delete an interview question"""
        with self.session_scope() as session:
            question = session.query(InterviewQuestion).filter_by(id=question_id).first()
            if question:
                session.delete(question)

    def search_jobs(self, search_term: str) -> List[dict]:
        """
        Search for jobs by company name, position, or notes.
        The search is case-insensitive and uses partial matching.
        """
        with self.session_scope() as session:
            # Create search conditions for each field
            search_term = f"%{search_term}%"
            jobs = session.query(Job).filter(
                or_(
                    Job.company.ilike(search_term),
                    Job.position.ilike(search_term),
                    Job.notes.ilike(search_term)
                )
            ).order_by(Job.updated_at.desc()).all()
            
            return [{
                'id': job.id,
                'company': job.company,
                'position': job.position,
                'status': job.status,
                'applied_date': job.applied_date if job.applied_date is not None else None,
                'notes': job.notes if job.notes is not None else None,
                'resume_versions': len(job.resume_versions)
            } for job in jobs] 