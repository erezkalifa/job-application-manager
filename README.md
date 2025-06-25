# Job Applications Manager

A Python-based application to efficiently manage job applications and track resume versions.

## Features

- Track job applications with detailed information
- Manage different versions of resumes for each application
- Store resumes in cloud storage (AWS S3)
- Track application status and history
- CLI interface with future web interface support
- Local SQLite database for data persistence

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up environment variables in `.env`:
   ```
   AWS_ACCESS_KEY_ID=your_access_key
   AWS_SECRET_ACCESS_KEY=your_secret_key
   AWS_BUCKET_NAME=your_bucket_name
   ```

## Usage

Run the application:

```bash
python app.py
```

## Project Structure

- `app.py`: Main entry point and CLI interface
- `models.py`: SQLAlchemy models for jobs and resume versions
- `storage.py`: Database operations and CRUD functionality
- `cloud.py`: AWS S3 integration for resume storage
- `utils.py`: Helper functions and utilities

## Database Schema

### Jobs

- id: Primary key
- company: Company name
- position: Job title
- status: Application status
- applied_date: Date of application
- notes: Additional notes
- created_at: Record creation timestamp
- updated_at: Record update timestamp

### ResumeVersions

- id: Primary key
- filename: Original filename
- s3_key: S3 storage key
- job_id: Foreign key to Jobs
- upload_date: Upload timestamp
- version: Version number
- notes: Version-specific notes
