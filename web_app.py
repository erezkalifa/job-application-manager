from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from models import init_db, ApplicationStatus
from storage import StorageManager
from cloud import S3Handler
import tempfile

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
                as_attachment=False,
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

if __name__ == '__main__':
    app.run(debug=True) 