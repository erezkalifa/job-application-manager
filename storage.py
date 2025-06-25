from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import logging
from datetime import datetime
from models import Job, ResumeVersion, ApplicationStatus

logger = logging.getLogger(__name__)

class StorageManager:
    def __init__(self, engine):
        """Initialize the storage manager with a database engine"""
        Session = sessionmaker(bind=engine)
        self.session = Session()

    def add_job(self, company, position, notes=None):
        """Add a new job application"""
        try:
            job = Job(
                company=company,
                position=position,
                status=ApplicationStatus.DRAFT,
                notes=notes
            )
            self.session.add(job)
            self.session.commit()
            return job
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error adding job: {str(e)}")
            raise

    def add_resume_version(self, job_id, filename, s3_key, notes=None):
        """Add a new resume version for a job"""
        try:
            # Get the current highest version number for this job
            current_max = self.session.query(ResumeVersion)\
                .filter_by(job_id=job_id)\
                .order_by(ResumeVersion.version.desc())\
                .first()
            
            new_version = 1 if not current_max else current_max.version + 1
            
            resume = ResumeVersion(
                filename=filename,
                s3_key=s3_key,
                job_id=job_id,
                version=new_version,
                notes=notes
            )
            self.session.add(resume)
            self.session.commit()
            return resume
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error adding resume version: {str(e)}")
            raise

    def update_job_status(self, job_id, status, applied_date=None):
        """Update the status of a job application"""
        try:
            job = self.session.query(Job).filter_by(id=job_id).first()
            if not job:
                raise ValueError(f"No job found with ID {job_id}")

            # Set the status as a string, not as an enum
            job.status = status.upper()

            # Only set applied_date if status is APPLIED and applied_date is not already set
            if status.upper() == "APPLIED" and getattr(job, 'applied_date', None) is None:
                setattr(job, 'applied_date', applied_date if applied_date is not None else datetime.utcnow())

            self.session.commit()
            return job
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating job status: {str(e)}")
            raise

    def get_job(self, job_id):
        """Get a job by ID"""
        return self.session.query(Job).filter_by(id=job_id).first()

    def get_all_jobs(self):
        """Get all jobs"""
        return self.session.query(Job).all()

    def get_job_resume_versions(self, job_id):
        """Get all resume versions for a job"""
        return self.session.query(ResumeVersion)\
            .filter_by(job_id=job_id)\
            .order_by(ResumeVersion.version)\
            .all()

    def delete_job(self, job_id):
        """Delete a job and its associated resume versions"""
        try:
            job = self.session.query(Job).filter_by(id=job_id).first()
            if not job:
                raise ValueError(f"No job found with ID {job_id}")
            
            self.session.delete(job)
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting job: {str(e)}")
            raise

    def update_resume_notes(self, job_id, version, notes):
        """Update the notes for a specific resume version"""
        try:
            resume = self.session.query(ResumeVersion)\
                .filter_by(job_id=job_id, version=version)\
                .first()
            
            if not resume:
                raise ValueError(f"No resume version {version} found for job {job_id}")
            
            resume.notes = notes
            self.session.commit()
            return resume
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating resume notes: {str(e)}")
            raise

    def close(self):
        """Close the database session"""
        self.session.close() 