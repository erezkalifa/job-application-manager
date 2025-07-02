from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List
import json
from pydantic import ValidationError
from datetime import datetime
import os
from sqlalchemy import update

from app.db.session import get_db
from app.schemas.job import JobCreate, JobResponse
from app.models.job import Job, JobStatus, ResumeVersion
from app.services.file_service import FileService

router = APIRouter()

@router.get("/", response_model=List[JobResponse])
async def get_jobs(db: Session = Depends(get_db)):
    try:
        jobs = db.query(Job).all()
        return jobs
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/", response_model=JobResponse)
async def create_job(
    company: str = Form(...),
    position: str = Form(...),
    notes: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    applied_date: Optional[str] = Form(None),
    resume: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    try:
        # Print received data for debugging
        print("Received data:", {
            "company": company,
            "position": position,
            "notes": notes,
            "status": status,
            "applied_date": applied_date
        })

        # Create job data
        job_data = {
            "company": company,
            "position": position,
            "notes": notes or "",
            "status": JobStatus.PENDING,  # Default status
            "applied_date": None  # Default applied_date
        }

        # Handle status if provided
        if status:
            try:
                job_data["status"] = JobStatus(status.lower())
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid status value. Must be one of: {', '.join([s.value for s in JobStatus])}"
                )

        # Handle applied_date if provided
        if applied_date:
            try:
                parsed_date = datetime.fromisoformat(applied_date.replace('Z', '+00:00'))
                job_data["applied_date"] = parsed_date
            except ValueError as e:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid date format: {str(e)}"
                )
        
        # Create and validate job data
        try:
            job_create = JobCreate(**job_data)
        except ValidationError as e:
            raise HTTPException(
                status_code=422,
                detail=str(e)
            )
        
        # Create job in database
        db_job = Job(**job_data)
        db.add(db_job)
        db.commit()
        db.refresh(db_job)

        # Handle resume upload if provided
        if resume:
            try:
                # Get next version number
                next_version = 1
                latest_version = db.query(ResumeVersion.version).filter(
                    ResumeVersion.job_id == db_job.id
                ).order_by(ResumeVersion.version.desc()).scalar()
                
                if latest_version:
                    next_version = latest_version + 1
                
                # Save the file
                job_id = db.query(Job.id).filter(Job.id == db_job.id).scalar()
                file_path, original_filename = await FileService.save_resume(
                    resume, 
                    job_id,
                    next_version
                )
                
                # Create resume version record
                resume_version = ResumeVersion(
                    job_id=db_job.id,
                    version=next_version,
                    filename=original_filename,
                    file_path=file_path,
                    upload_date=datetime.utcnow()
                )
                db.add(resume_version)
                db.commit()
                
            except Exception as e:
                print(f"Error uploading resume: {str(e)}")  # Debug print
                # If file upload fails, delete the job and raise error
                db.delete(db_job)
                db.commit()
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to upload resume: {str(e)}"
                )

        return db_job
    except Exception as e:
        print(f"Error in create_job: {str(e)}")  # Debug print
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while creating the job: {str(e)}"
        )

@router.get("/{job_id}/resume/{version_id}")
async def view_resume(job_id: int, version_id: int, db: Session = Depends(get_db)):
    """View resume in browser"""
    resume_version = db.query(ResumeVersion).filter(
        ResumeVersion.id == version_id,
        ResumeVersion.job_id == job_id
    ).first()
    
    if not resume_version:
        raise HTTPException(status_code=404, detail="Resume version not found")
    
    file_path = str(resume_version.file_path)
    filename = str(resume_version.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Resume file not found")
    
    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=filename,
        headers={
            "Content-Disposition": "inline"
        }
    )

@router.get("/{job_id}/resume/{version_id}/download")
async def download_resume(job_id: int, version_id: int, db: Session = Depends(get_db)):
    """Download resume"""
    resume_version = db.query(ResumeVersion).filter(
        ResumeVersion.id == version_id,
        ResumeVersion.job_id == job_id
    ).first()
    
    if not resume_version:
        raise HTTPException(status_code=404, detail="Resume version not found")
    
    file_path = str(resume_version.file_path)
    filename = str(resume_version.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Resume file not found")
    
    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=filename
    )

@router.delete("/{job_id}/resume/{version_id}")
async def delete_resume(job_id: int, version_id: int, db: Session = Depends(get_db)):
    """Delete a specific resume version"""
    print(f"Attempting to delete resume version {version_id} for job {job_id}")  # Debug log
    
    # Get the resume version
    resume_version = db.query(ResumeVersion).filter(
        ResumeVersion.id == version_id,
        ResumeVersion.job_id == job_id
    ).first()
    
    if not resume_version:
        print(f"Resume version not found: version_id={version_id}, job_id={job_id}")  # Debug log
        raise HTTPException(status_code=404, detail="Resume version not found")
    
    file_path = str(resume_version.file_path)
    print(f"Found resume at path: {file_path}")  # Debug log
    
    try:
        # Delete physical file if it exists
        if os.path.exists(file_path):
            print(f"Deleting file at: {file_path}")  # Debug log
            os.remove(file_path)
        else:
            print(f"File does not exist at: {file_path}")  # Debug log
        
        # Delete the database record
        print(f"Deleting database record")  # Debug log
        db.delete(resume_version)
        db.commit()
        
        return {"message": "Resume deleted successfully"}
    except Exception as e:
        print(f"Error during deletion: {str(e)}")  # Debug log
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete resume: {str(e)}"
        )

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, db: Session = Depends(get_db)):
    """Get a specific job by ID"""
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.delete("/{job_id}")
async def delete_job(job_id: int, db: Session = Depends(get_db)):
    """Delete a specific job and all its associated resume versions"""
    try:
        # Get the job
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Get all resume versions for this job
        resume_versions = db.query(ResumeVersion).filter(ResumeVersion.job_id == job_id).all()
        
        # Delete physical resume files
        for version in resume_versions:
            file_path = str(version.file_path)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Delete the job (this will cascade delete resume versions due to SQLAlchemy relationship)
        db.delete(job)
        db.commit()
        
        return {"message": "Job deleted successfully"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete job: {str(e)}"
        )

@router.post("/{job_id}/resume")
async def upload_resume(
    job_id: int,
    resume: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a new resume version for a job"""
    try:
        # Check if job exists
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get next version number
        next_version = 1
        latest_version = db.query(ResumeVersion.version).filter(
            ResumeVersion.job_id == job_id
        ).order_by(ResumeVersion.version.desc()).scalar()
        
        if latest_version:
            next_version = latest_version + 1
        
        # Save the file
        file_path, original_filename = await FileService.save_resume(
            resume, 
            job_id,
            next_version
        )
        
        # Create resume version record
        resume_version = ResumeVersion(
            job_id=job_id,
            version=next_version,
            filename=original_filename,
            file_path=file_path,
            upload_date=datetime.utcnow()
        )
        db.add(resume_version)
        db.commit()
        db.refresh(resume_version)
        
        # Return the updated job
        return job

    except Exception as e:
        print(f"Error uploading resume: {str(e)}")  # Debug print
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload resume: {str(e)}"
        ) 