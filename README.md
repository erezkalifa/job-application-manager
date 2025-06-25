# Job Applications Manager

A web-based application to help job seekers manage their job applications and track different versions of their resumes. Built with Flask and AWS S3 for file storage.

## Features

- Track job applications with company name, position, and status
- Upload and manage multiple versions of resumes for each job application
- Add notes for each job application and resume version
- Store resumes securely in AWS S3
- Clean and intuitive web interface
- Status tracking for each application
- View and download resume versions

## Technologies Used

- Python 3.x
- Flask
- SQLAlchemy
- AWS S3
- Bootstrap 5
- SQLite

## Setup

1. Clone the repository:

```bash
git clone [your-repo-url]
cd job-applications-manager
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Set up environment variables:
   Create a `.env` file in the root directory with the following:

```
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_BUCKET_NAME=your_bucket_name
```

5. Initialize the database:

```bash
python models.py
```

6. Run the application:

```bash
python web_app.py
```

The application will be available at `http://localhost:5000`

## Usage

1. **Adding a Job Application**

   - Click "Add Job" button
   - Fill in company name, position, and optional notes
   - Select the application status
   - Upload an initial resume version if available

2. **Managing Resume Versions**

   - Navigate to a specific job application
   - Upload new resume versions
   - Add notes for each version
   - View or download any version

3. **Tracking Application Status**
   - Update status directly from the job details page
   - Track application progress from initial submission to offer/rejection

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

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
