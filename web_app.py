from flask import Flask, render_template, request, redirect, url_for, flash, send_file, after_this_request
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from models import init_db, ApplicationStatus, InterviewStageType, InterviewStageStatus
from storage import StorageManager
from cloud import S3Handler
from typing import Optional

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
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    search_term = request.args.get('search', '').strip()
    if search_term:
        jobs = storage.search_jobs(search_term)
    else:
        jobs = storage.get_all_jobs()
    return render_template('index.html', jobs=jobs, ApplicationStatus=ApplicationStatus, search_term=search_term)

@app.route('/add_job', methods=['GET', 'POST'])
def add_job():
    if request.method == 'POST':
        company = request.form['company']
        position = request.form['position']
        status = request.form['status']
        notes = request.form.get('notes', '')

        # Convert status string to enum
        status = ApplicationStatus[status]

        # Create new job
        job = storage.create_job(
            company=company,
            position=position,
            status=status,
            applied_date=None,  # Will be set when status changes to APPLIED
            notes=notes
        )

        # Handle resume file upload
        if 'resume' in request.files:
            file = request.files['resume']
            if file and file.filename:
                # Save file temporarily
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                # Upload to S3
                s3_key = s3.upload_file(filepath, job['id'])
                
                # Create resume version
                storage.create_resume_version(
                    job_id=job['id'],
                    filename=filename,
                    s3_key=s3_key,
                    notes=request.form.get('resume_notes', '')
                )

                # Clean up temporary file
                os.remove(filepath)

        flash('Job application added successfully!', 'success')
        return redirect(url_for('view_job', job_id=job['id']))

    return render_template('add_job.html', ApplicationStatus=ApplicationStatus)

@app.route('/job/<int:job_id>')
def view_job(job_id):
    job = storage.get_job(job_id)
    if job is None:
        flash('Job not found!', 'error')
        return redirect(url_for('index'))
    return render_template('view_job.html', job=job, ApplicationStatus=ApplicationStatus)

@app.route('/job/<int:job_id>/update', methods=['POST'])
def update_job(job_id):
    job = storage.get_job(job_id)
    if job is None:
        flash('Job not found!', 'error')
        return redirect(url_for('index'))

    # Get current values
    company = request.form.get('company', job['company'])
    position = request.form.get('position', job['position'])
    status_str = request.form.get('status', job['status'].name)
    status = ApplicationStatus[status_str]  # Convert string to enum
    applied_date = request.form.get('applied_date', None)
    notes = request.form.get('notes', job['notes'])

    # Convert empty date to None, keep existing date if not provided
    if applied_date:
        applied_date = datetime.strptime(applied_date, '%Y-%m-%d')
    elif applied_date is None and job['applied_date']:
        applied_date = job['applied_date']
    else:
        applied_date = None

    storage.update_job(
        job_id=job_id,
        company=company,
        position=position,
        status=status,
        applied_date=applied_date,
        notes=notes
    )

    flash('Job updated successfully!', 'success')
    return redirect(url_for('view_job', job_id=job_id))

@app.route('/job/<int:job_id>/delete', methods=['POST'])
def delete_job(job_id):
    job = storage.get_job(job_id)
    if job is None:
        flash('Job not found!', 'error')
        return redirect(url_for('index'))

    # Delete all resume versions from S3
    for version in job['resume_versions']:
        s3.delete_file(version['s3_key'])

    # Delete job from database
    storage.delete_job(job_id)

    flash('Job deleted successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/job/<int:job_id>/add_resume', methods=['POST'])
def add_resume(job_id):
    job = storage.get_job(job_id)
    if job is None:
        flash('Job not found!', 'error')
        return redirect(url_for('index'))

    if 'resume' not in request.files:
        flash('No resume file uploaded!', 'error')
        return redirect(url_for('view_job', job_id=job_id))

    file = request.files['resume']
    if not file or not file.filename:
        flash('No resume file selected!', 'error')
        return redirect(url_for('view_job', job_id=job_id))

    # Save file temporarily
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # Upload to S3 and create resume version
    s3_key = s3.upload_file(filepath, job_id)
    
    # Create resume version
    storage.create_resume_version(
        job_id=job_id,
        filename=filename,
        s3_key=s3_key,
        notes=request.form.get('resume_notes', '')
    )

    # Clean up temporary file
    os.remove(filepath)

    flash('Resume version added successfully!', 'success')
    return redirect(url_for('view_job', job_id=job_id))

@app.route('/resume/<int:version_id>/view')
def view_resume(version_id):
    version = storage.get_resume_version(version_id)
    if version is None:
        flash('Resume version not found!', 'error')
        return redirect(url_for('index'))

    # Download from S3 to temporary file
    filename = version['filename']
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        s3.download_file(version['s3_key'], filepath)
    except FileNotFoundError:
        flash('Resume file not found in storage. The file might have been deleted or moved.', 'error')
        return redirect(url_for('view_job', job_id=version['job_id']))
    except Exception as e:
        flash(f'Error downloading resume: {str(e)}', 'error')
        return redirect(url_for('view_job', job_id=version['job_id']))

    # For PDFs, display inline. For other files, download
    if filename.lower().endswith('.pdf'):
        try:
            return send_file(
                filepath,
                as_attachment=False,
                mimetype='application/pdf'
            )
        finally:
            # Try to remove the file, but don't fail if we can't
            try:
                os.remove(filepath)
            except (OSError, PermissionError):
                pass
    else:
        try:
            return send_file(
                filepath,
                as_attachment=True,
                download_name=filename
            )
        finally:
            # Try to remove the file, but don't fail if we can't
            try:
                os.remove(filepath)
            except (OSError, PermissionError):
                pass

@app.route('/resume/<int:version_id>')
def download_resume(version_id):
    version = storage.get_resume_version(version_id)
    if version is None:
        flash('Resume version not found!', 'error')
        return redirect(url_for('index'))

    # Download from S3 to temporary file
    filename = version['filename']
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        s3.download_file(version['s3_key'], filepath)
    except FileNotFoundError:
        flash('Resume file not found in storage. The file might have been deleted or moved.', 'error')
        return redirect(url_for('view_job', job_id=version['job_id']))
    except Exception as e:
        flash(f'Error downloading resume: {str(e)}', 'error')
        return redirect(url_for('view_job', job_id=version['job_id']))

    try:
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename
        )
    finally:
        # Try to remove the file, but don't fail if we can't
        try:
            os.remove(filepath)
        except (OSError, PermissionError):
            pass

@app.route('/resume/<int:version_id>/delete', methods=['POST'])
def delete_resume(version_id):
    version = storage.get_resume_version(version_id)
    if version is None:
        flash('Resume version not found!', 'error')
        return redirect(url_for('index'))

    job_id = version['job_id']

    # Delete file from S3
    s3.delete_file(version['s3_key'])

    # Delete version from database
    storage.delete_resume_version(version_id)

    flash('Resume version deleted successfully!', 'success')
    return redirect(url_for('view_job', job_id=job_id))

@app.route('/job/<int:job_id>/interview_stages')
def interview_stages(job_id):
    job = storage.get_job(job_id)
    if job is None:
        flash('Job not found!', 'error')
        return redirect(url_for('index'))
    
    stages = storage.get_interview_stages(job_id)
    return render_template('interview_stages.html', 
                         job=job,
                         stages=stages,
                         stage_types=InterviewStageType,
                         stage_statuses=InterviewStageStatus)

@app.route('/job/<int:job_id>/add_stage', methods=['POST'])
def add_interview_stage(job_id):
    job = storage.get_job(job_id)
    if job is None:
        flash('Job not found!', 'error')
        return redirect(url_for('index'))

    stage_type = request.form.get('stage_type')
    if not stage_type:
        flash('Stage type is required!', 'error')
        return redirect(url_for('interview_stages', job_id=job_id))

    # Convert string to enum
    stage_type = InterviewStageType[stage_type]
    status = InterviewStageStatus[request.form.get('status', 'UPCOMING')]

    # Convert scheduled_date string to datetime object if provided
    scheduled_date = request.form.get('scheduled_date')
    if scheduled_date and scheduled_date.strip():
        try:
            scheduled_date = datetime.strptime(scheduled_date, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid date format!', 'error')
            return redirect(url_for('interview_stages', job_id=job_id))
    else:
        scheduled_date = None

    storage.create_interview_stage(
        job_id=job_id,
        stage_type=stage_type,
        custom_stage_name=request.form.get('custom_stage_name'),
        scheduled_date=scheduled_date,
        status=status,
        key_takeaway=request.form.get('key_takeaway'),
        general_notes=request.form.get('general_notes')
    )

    flash('Interview stage added successfully!', 'success')
    return redirect(url_for('interview_stages', job_id=job_id))

@app.route('/interview_stage/<int:stage_id>/update', methods=['POST'])
def update_interview_stage(stage_id):
    stage = storage.get_interview_stage(stage_id)
    if stage is None:
        flash('Interview stage not found!', 'error')
        return redirect(url_for('index'))

    stage_type = request.form['stage_type']
    custom_stage_name = request.form.get('custom_stage_name') if stage_type == InterviewStageType.CUSTOM.name else None
    scheduled_date = request.form.get('scheduled_date')
    status = request.form.get('status')
    completed_date = request.form.get('completed_date') if status == InterviewStageStatus.COMPLETED.name else None
    key_takeaway = request.form.get('key_takeaway')
    general_notes = request.form.get('general_notes')

    # Convert empty dates to None
    if scheduled_date and scheduled_date.strip():
        try:
            scheduled_date = datetime.strptime(scheduled_date, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid scheduled date format!', 'error')
            return redirect(url_for('interview_stages', job_id=stage['job_id']))
    else:
        scheduled_date = None

    if completed_date and completed_date.strip():
        try:
            completed_date = datetime.strptime(completed_date, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid completed date format!', 'error')
            return redirect(url_for('interview_stages', job_id=stage['job_id']))
    else:
        completed_date = None

    storage.update_interview_stage(
        stage_id=stage_id,
        stage_type=InterviewStageType[stage_type],
        custom_stage_name=custom_stage_name,
        scheduled_date=scheduled_date,
        completed_date=completed_date,
        status=InterviewStageStatus[status] if status else None,
        key_takeaway=key_takeaway,
        general_notes=general_notes
    )

    flash('Interview stage updated successfully!', 'success')
    return redirect(url_for('interview_stages', job_id=stage['job_id']))

@app.route('/interview_stage/<int:stage_id>/delete', methods=['POST'])
def delete_interview_stage(stage_id):
    stage = storage.get_interview_stage(stage_id)
    if stage is None:
        flash('Interview stage not found!', 'error')
        return redirect(url_for('index'))

    job_id = stage['job_id']
    storage.delete_interview_stage(stage_id)

    flash('Interview stage deleted successfully!', 'success')
    return redirect(url_for('interview_stages', job_id=job_id))

@app.route('/interview_stage/<int:stage_id>/add_question', methods=['POST'])
def add_interview_question(stage_id):
    stage = storage.get_interview_stage(stage_id)
    if stage is None:
        flash('Interview stage not found!', 'error')
        return redirect(url_for('index'))

    question = request.form.get('question')
    if not question:
        flash('Question is required!', 'error')
        return redirect(url_for('interview_stages', job_id=stage['job_id']))

    storage.create_interview_question(
        stage_id=stage_id,
        question=question,
        answer=request.form.get('answer'),
        notes=request.form.get('notes')
    )

    flash('Interview question added successfully!', 'success')
    return redirect(url_for('interview_stages', job_id=stage['job_id']))

@app.route('/interview_question/<int:question_id>/update', methods=['POST'])
def update_interview_question(question_id):
    question = storage.get_interview_question(question_id)
    if question is None:
        flash('Interview question not found!', 'error')
        return redirect(url_for('index'))

    question_text = request.form.get('question')
    answer = request.form.get('answer')
    notes = request.form.get('notes')

    storage.update_interview_question(
        question_id=question_id,
        question=question_text,
        answer=answer,
        notes=notes
    )

    flash('Interview question updated successfully!', 'success')
    return redirect(url_for('interview_stages', job_id=question['stage']['job_id']))

@app.route('/interview_question/<int:question_id>/delete', methods=['POST'])
def delete_interview_question(question_id):
    question = storage.get_interview_question(question_id)
    if question is None:
        flash('Interview question not found!', 'error')
        return redirect(url_for('index'))

    job_id = question['stage']['job_id']
    storage.delete_interview_question(question_id)

    flash('Interview question deleted successfully!', 'success')
    return redirect(url_for('interview_stages', job_id=job_id))

@app.route('/interview_stage/<int:stage_id>/data')
def get_interview_stage_data(stage_id):
    stage = storage.get_interview_stage(stage_id)
    if stage is None:
        return {'error': 'Stage not found'}, 404
    
    return {
        'stage_type': stage['stage_type'].name,
        'custom_stage_name': stage['custom_stage_name'],
        'scheduled_date': stage['scheduled_date'].strftime('%Y-%m-%dT%H:%M') if stage['scheduled_date'] else '',
        'status': stage['status'].name,
        'key_takeaway': stage['key_takeaway'],
        'general_notes': stage['general_notes'],
        'questions': [{'question': q['question']} for q in stage['questions']]
    }

if __name__ == '__main__':
    app.run(debug=True) 