from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from models import init_db, ApplicationStatus, InterviewStageType, InterviewStageStatus
from storage import StorageManager
from cloud import S3Handler
from email_manager import create_email_manager
import tempfile
import threading

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Required for flash messages

# Initialize database and storage managers
engine = init_db()
storage = StorageManager(engine)
s3 = S3Handler()

# Ensure upload folder exists
UPLOAD_FOLDER = 'temp_uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def index():
    jobs = storage.get_all_jobs()
    return render_template('index.html', jobs=jobs, ApplicationStatus=ApplicationStatus)

@app.route('/add_job', methods=['GET', 'POST'])
def add_job():
    if request.method == 'POST':
        company = request.form['company']
        position = request.form['position']
        notes = request.form['notes']
        status = request.form['status']
        
        try:
            # Create the job first
            job = storage.add_job(company, position, notes)
            
            # Update the status if it's not DRAFT
            if status != 'DRAFT':
                storage.update_job_status(job.id, status)
            
            # Handle resume upload if provided
            if 'resume' in request.files and request.files['resume'].filename:
                file = request.files['resume']
                if not file.filename:
                    flash('No filename provided', 'error')
                else:
                    filename = secure_filename(file.filename)
                    temp_path = os.path.join(UPLOAD_FOLDER, filename)
                    
                    try:
                        # Save file temporarily
                        file.save(temp_path)
                        
                        # Upload to S3
                        s3_key = s3.upload_file(temp_path, job.id)
                        
                        # Add to database
                        resume_notes = request.form.get('resume_notes', '')
                        storage.add_resume_version(job.id, filename, s3_key, resume_notes)
                        
                    finally:
                        # Clean up temp file
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
            
            flash('Job application added successfully!', 'success')
            return redirect(url_for('view_job', job_id=job.id))
        except Exception as e:
            flash(f'Error adding job: {str(e)}', 'error')
    
    return render_template('add_job.html', ApplicationStatus=ApplicationStatus)

@app.route('/job/<int:job_id>')
def view_job(job_id):
    job = storage.get_job(job_id)
    if not job:
        flash('Job not found!', 'error')
        return redirect(url_for('index'))
    
    resumes = storage.get_job_resume_versions(job_id)
    return render_template('view_job.html', job=job, resumes=resumes, ApplicationStatus=ApplicationStatus)

@app.route('/job/<int:job_id>/add_resume', methods=['POST'])
def add_resume(job_id):
    # Get the notes first
    notes = request.form.get('notes', '')
    
    # Check if we're just updating notes without a new file
    if 'resume' not in request.files or not request.files['resume'].filename:
        if not notes.strip():
            flash('Please provide either a resume file or notes to update.', 'error')
            return redirect(url_for('view_job', job_id=job_id))
            
        try:
            # Get the latest resume version
            resumes = storage.get_job_resume_versions(job_id)
            if not resumes:
                flash('No resume versions found to update notes.', 'error')
                return redirect(url_for('view_job', job_id=job_id))
                
            latest_resume = resumes[-1]  # Get the latest version
            storage.update_resume_notes(job_id, latest_resume.version, notes)
            flash('Version notes updated successfully!', 'success')
        except Exception as e:
            flash(f'Error updating version notes: {str(e)}', 'error')
        return redirect(url_for('view_job', job_id=job_id))
    
    # Handle new resume upload
    file = request.files['resume']
    try:
        # Save file temporarily
        if not file.filename:
            flash('No file selected', 'error')
            return redirect(url_for('view_job', job_id=job_id))
        
        filename = secure_filename(file.filename)
        temp_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(temp_path)
        
        # Upload to S3
        s3_key = s3.upload_file(temp_path, job_id)
        
        # Add to database
        storage.add_resume_version(job_id, filename, s3_key, notes)
        
        # Clean up temp file
        os.remove(temp_path)
        
        flash('Resume uploaded successfully!', 'success')
    except Exception as e:
        flash(f'Error uploading resume: {str(e)}', 'error')
    
    return redirect(url_for('view_job', job_id=job_id))

@app.route('/job/<int:job_id>/update_status', methods=['POST'])
def update_status(job_id):
    status = request.form['status']
    applied_date = None
    if status == 'APPLIED':
        applied_date = datetime.now()
    
    try:
        storage.update_job_status(job_id, status, applied_date)
        flash('Status updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating status: {str(e)}', 'error')
    
    return redirect(url_for('view_job', job_id=job_id))

@app.route('/job/<int:job_id>/delete', methods=['POST'])
def delete_job(job_id):
    try:
        job = storage.get_job(job_id)
        if not job:
            flash('Job not found!', 'error')
            return redirect(url_for('index'))
        
        # Delete associated files from S3
        for version in job.resume_versions:
            s3.delete_file(version.s3_key)
        
        # Delete from database
        storage.delete_job(job_id)
        flash('Job deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting job: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/job/<int:job_id>/resume/<int:version>/view')
def view_resume(job_id, version):
    try:
        # Get the resume version
        job = storage.get_job(job_id)
        if not job:
            flash('Job not found!', 'error')
            return redirect(url_for('index'))
        
        resume = next((r for r in job.resume_versions if r.version == version), None)
        if not resume:
            flash('Resume version not found!', 'error')
            return redirect(url_for('view_job', job_id=job_id))
        
        # Create a temporary file to store the downloaded resume
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"resume_view_{job_id}_{version}_{os.urandom(4).hex()}")
        
        try:
            # Download from S3
            s3.download_file(resume.s3_key, temp_path)
            
            # Send the file to the user
            return send_file(
                temp_path,
                download_name=resume.filename,
                as_attachment=False
            )
        finally:
            # Clean up temp file in a separate thread to ensure it's deleted
            def cleanup():
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                except:
                    pass  # Ignore cleanup errors
            
            threading.Thread(target=cleanup).start()
            
    except Exception as e:
        flash(f'Error viewing resume: {str(e)}', 'error')
        return redirect(url_for('view_job', job_id=job_id))

@app.route('/job/<int:job_id>/resume/<int:version>/download')
def download_resume(job_id, version):
    try:
        # Get the resume version
        job = storage.get_job(job_id)
        if not job:
            flash('Job not found!', 'error')
            return redirect(url_for('index'))
        
        resume = next((r for r in job.resume_versions if r.version == version), None)
        if not resume:
            flash('Resume version not found!', 'error')
            return redirect(url_for('view_job', job_id=job_id))
        
        # Create a temporary file to store the downloaded resume
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"resume_download_{job_id}_{version}_{os.urandom(4).hex()}")
        
        try:
            # Download from S3
            s3.download_file(resume.s3_key, temp_path)
            
            # Send the file to the user
            return send_file(
                temp_path,
                download_name=resume.filename,
                as_attachment=True,
                max_age=0
            )
        except Exception as e:
            # Only try to remove the file if something went wrong
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass  # Ignore cleanup errors
            raise e
            
    except Exception as e:
        flash(f'Error downloading resume: {str(e)}', 'error')
        return redirect(url_for('view_job', job_id=job_id))

@app.route('/job/<int:job_id>/resume/<int:version>/update_notes', methods=['POST'])
def update_resume_notes(job_id, version):
    try:
        notes = request.form.get('notes', '')
        storage.update_resume_notes(job_id, version, notes)
        flash('Resume notes updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating resume notes: {str(e)}', 'error')
    
    return redirect(url_for('view_job', job_id=job_id))

@app.route('/job/<int:job_id>/update_version_notes', methods=['POST'])
def update_version_notes(job_id):
    try:
        notes = request.form.get('notes', '')
        if not notes.strip():
            flash('Please enter some notes to update.', 'error')
            return redirect(url_for('view_job', job_id=job_id))
            
        # Get the latest resume version
        resumes = storage.get_job_resume_versions(job_id)
        if not resumes:
            flash('No resume versions found to update notes.', 'error')
            return redirect(url_for('view_job', job_id=job_id))
            
        latest_resume = resumes[-1]  # Get the latest version
        storage.update_resume_notes(job_id, latest_resume.version, notes)
        flash('Version notes updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating version notes: {str(e)}', 'error')
    
    return redirect(url_for('view_job', job_id=job_id))

@app.route('/search_emails')
def search_emails():
    # Get search parameters from query string
    keyword = request.args.get('keyword', '')
    max_results = int(request.args.get('max_results', 50))
    search_subject = request.args.get('search_subject') is not None
    search_body = request.args.get('search_body') is not None
    search_sender = request.args.get('search_sender') is not None
    
    emails = []
    if keyword:
        try:
            # Create email manager instance
            email_mgr = create_email_manager()
            
            # Search for emails
            emails = email_mgr.search_emails(
                keyword=keyword,
                max_results=max_results,
                search_subject=search_subject,
                search_body=search_body,
                search_sender=search_sender
            )
        except Exception as e:
            flash(f'Error searching emails: {str(e)}', 'error')
    
    return render_template('search_emails.html',
                         emails=emails,
                         keyword=keyword,
                         max_results=max_results,
                         search_subject=search_subject,
                         search_body=search_body,
                         search_sender=search_sender)

@app.route('/search_linkedin')
def search_linkedin():
    try:
        hours = int(request.args.get('hours', '24'))
        max_results = int(request.args.get('max_results', '50'))
        
        # Create email manager instance
        email_mgr = create_email_manager()
        
        # Search for LinkedIn emails
        emails = email_mgr.search_recent_linkedin(
            hours=hours,
            max_results=max_results
        )
        
        return render_template('search_linkedin.html',
                            emails=emails,
                            hours=hours,
                            max_results=max_results,
                            error_message=None)
        
    except ValueError as e:
        flash('Please enter valid numbers for hours and maximum results.', 'error')
        return render_template('search_linkedin.html',
                            emails=[],
                            hours=24,
                            max_results=50,
                            error_message='Invalid input parameters')
    except Exception as e:
        error_msg = str(e)
        if 'authentication failed' in error_msg.lower():
            error_msg = 'Email authentication failed. Please check your credentials and make sure you have set up an App Password if using Gmail with 2-factor authentication.'
        elif 'connection refused' in error_msg.lower():
            error_msg = 'Could not connect to email server. Please check your internet connection and try again.'
        
        flash(f'Error searching LinkedIn emails: {error_msg}', 'error')
        return render_template('search_linkedin.html',
                            emails=[],
                            hours=24,
                            max_results=50,
                            error_message=error_msg)

@app.route('/job/<int:job_id>/resume/<int:version>/delete', methods=['POST'])
def delete_resume(job_id, version):
    try:
        # Delete from database and get S3 key
        s3_key = storage.delete_resume_version(job_id, version)
        
        # Delete from S3
        s3.delete_file(s3_key)
        
        flash('Resume version deleted successfully!', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Error deleting resume version: {str(e)}', 'error')
    
    return redirect(url_for('view_job', job_id=job_id))

@app.route('/job/<int:job_id>/interview_stages')
def view_interview_stages(job_id):
    """View interview stages for a job"""
    try:
        job = storage.get_job(job_id)
        if not job:
            flash('Job not found!', 'error')
            return redirect(url_for('index'))
        
        stages = storage.get_interview_stages(job_id)
        return render_template('interview_stages.html',
                             job=job,
                             stages=stages,
                             stage_types=InterviewStageType,
                             stage_statuses=InterviewStageStatus)
    except Exception as e:
        flash(f'Error viewing interview stages: {str(e)}', 'error')
        return redirect(url_for('view_job', job_id=job_id))

@app.route('/job/<int:job_id>/interview_stage/add', methods=['POST'])
def add_interview_stage(job_id):
    """Add a new interview stage"""
    try:
        stage_type = InterviewStageType[request.form['stage_type']]
        custom_stage_name = request.form.get('custom_stage_name') if stage_type == InterviewStageType.CUSTOM else None
        scheduled_date = None
        if request.form.get('scheduled_date'):
            try:
                scheduled_date = datetime.fromisoformat(request.form['scheduled_date'])
            except ValueError:
                pass
        
        # Create the stage
        stage = storage.add_interview_stage(
            job_id=job_id,
            stage_type=stage_type,
            scheduled_date=scheduled_date,
            custom_stage_name=custom_stage_name
        )
        
        # Add questions if provided
        questions = request.form.getlist('questions[]')
        for question in questions:
            if question.strip():  # Only add non-empty questions
                storage.add_interview_question(stage.id, question)
        
        # Update other fields
        storage.update_interview_stage(
            stage.id,
            status=InterviewStageStatus[request.form['status']],
            key_takeaway=request.form.get('key_takeaway'),
            general_notes=request.form.get('general_notes')
        )
        
        flash('Interview stage added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding interview stage: {str(e)}', 'error')
    
    return redirect(url_for('view_interview_stages', job_id=job_id))

@app.route('/job/<int:job_id>/interview_stage/<int:stage_id>')
def get_interview_stage(job_id, stage_id):
    """Get interview stage details"""
    try:
        stages = storage.get_interview_stages(job_id)
        stage = next((s for s in stages if s.id == stage_id), None)
        
        if not stage:
            return jsonify({'error': 'Stage not found'}), 404
        
        return jsonify({
            'stage_type': stage.stage_type.name,
            'custom_stage_name': stage.custom_stage_name,
            'status': stage.status.name,
            'scheduled_date': stage.scheduled_date.isoformat() if stage.scheduled_date else None,
            'completed_date': stage.completed_date.isoformat() if stage.completed_date else None,
            'key_takeaway': stage.key_takeaway,
            'general_notes': stage.general_notes,
            'questions': [{'id': q.id, 'question': q.question} for q in stage.questions]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/job/<int:job_id>/interview_stage/<int:stage_id>/update', methods=['POST'])
def update_interview_stage(job_id, stage_id):
    """Update an interview stage"""
    try:
        stage_type = InterviewStageType[request.form['stage_type']]
        custom_stage_name = request.form.get('custom_stage_name') if stage_type == InterviewStageType.CUSTOM else None
        scheduled_date = None
        if request.form.get('scheduled_date'):
            try:
                scheduled_date = datetime.fromisoformat(request.form['scheduled_date'])
            except ValueError:
                pass
        
        # Update the stage
        storage.update_interview_stage(
            stage_id,
            stage_type=stage_type,
            custom_stage_name=custom_stage_name,
            scheduled_date=scheduled_date,
            status=InterviewStageStatus[request.form['status']],
            key_takeaway=request.form.get('key_takeaway'),
            general_notes=request.form.get('general_notes')
        )
        
        # Handle questions
        # First, get existing questions
        stage = next((s for s in storage.get_interview_stages(job_id) if s.id == stage_id), None)
        if stage:
            # Delete existing questions
            for question in stage.questions:
                storage.delete_interview_question(question.id)
            
            # Add new questions
            questions = request.form.getlist('questions[]')
            for question in questions:
                if question.strip():  # Only add non-empty questions
                    storage.add_interview_question(stage_id, question)
        
        flash('Interview stage updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating interview stage: {str(e)}', 'error')
    
    return redirect(url_for('view_interview_stages', job_id=job_id))

@app.route('/job/<int:job_id>/interview_stage/<int:stage_id>/delete', methods=['POST'])
def delete_interview_stage(job_id, stage_id):
    """Delete an interview stage"""
    try:
        storage.delete_interview_stage(stage_id)
        flash('Interview stage deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting interview stage: {str(e)}', 'error')
    
    return redirect(url_for('view_interview_stages', job_id=job_id))

if __name__ == '__main__':
    app.run(debug=True) 