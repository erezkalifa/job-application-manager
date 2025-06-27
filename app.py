import os
import click
from rich.console import Console
from rich.table import Table
from datetime import datetime
from dotenv import load_dotenv
from models import init_db, ApplicationStatus
from storage import StorageManager
from cloud import S3Handler
from email_manager import create_email_manager

# Load environment variables
load_dotenv()

# Initialize console for rich output
console = Console()

# Initialize database and storage managers
engine = init_db()
storage = StorageManager(engine)
s3 = S3Handler()

def validate_file(ctx, param, value):
    """Validate that the file exists"""
    if value and not os.path.exists(value):
        raise click.BadParameter(f"File {value} does not exist")
    return value

@click.group()
def cli():
    """Job Applications Manager - Track your job applications and resume versions"""
    pass

@cli.command()
@click.option('--company', prompt='Company name', help='Name of the company')
@click.option('--position', prompt='Position', help='Job position/title')
@click.option('--notes', help='Additional notes about the job')
def add_job(company, position, notes):
    """Add a new job application"""
    try:
        job = storage.add_job(company, position, notes)
        console.print(f"[green]Successfully added job application for {company} - {position}[/green]")
        console.print(f"Job ID: {job.id}")
    except Exception as e:
        console.print(f"[red]Error adding job: {str(e)}[/red]")

@cli.command()
@click.option('--job-id', prompt='Job ID', type=int, help='ID of the job application')
@click.option('--resume', prompt='Resume file path', type=click.Path(exists=True), callback=validate_file,
              help='Path to the resume file')
@click.option('--notes', help='Notes about this resume version')
def add_resume(job_id, resume, notes):
    """Upload a new resume version for a job application"""
    try:
        # First check if job exists
        job = storage.get_job(job_id)
        if not job:
            console.print(f"[red]No job found with ID {job_id}[/red]")
            return

        # Upload to S3
        s3_key = s3.upload_file(resume, job_id)
        
        # Add to database
        resume_version = storage.add_resume_version(
            job_id=job_id,
            filename=os.path.basename(resume),
            s3_key=s3_key,
            notes=notes
        )
        
        console.print(f"[green]Successfully uploaded resume version {resume_version.version}[/green]")
    except Exception as e:
        console.print(f"[red]Error uploading resume: {str(e)}[/red]")

@cli.command()
@click.option('--job-id', prompt='Job ID', type=int, help='ID of the job application')
@click.option('--status', prompt='New status', 
              type=click.Choice([s.name for s in ApplicationStatus], case_sensitive=False),
              help='New application status')
@click.option('--applied-date', type=click.DateTime(formats=["%Y-%m-%d"]),
              help='Date of application (YYYY-MM-DD)')
def update_status(job_id, status, applied_date):
    """Update the status of a job application"""
    try:
        job = storage.update_job_status(job_id, status, applied_date)
        console.print(f"[green]Successfully updated status for {job.company} - {job.position}[/green]")
        console.print(f"New status: {job.status.value}")
    except Exception as e:
        console.print(f"[red]Error updating status: {str(e)}[/red]")

@cli.command()
def list_jobs():
    """List all job applications"""
    try:
        jobs = storage.get_all_jobs()
        
        if not jobs:
            console.print("[yellow]No job applications found[/yellow]")
            return

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim")
        table.add_column("Company")
        table.add_column("Position")
        table.add_column("Status")
        table.add_column("Applied Date")
        table.add_column("Resume Versions")

        for job in jobs:
            resume_count = len(job.resume_versions)
            applied_date = job.applied_date.strftime("%Y-%m-%d") if getattr(job, 'applied_date', None) else "N/A"
            
            table.add_row(
                str(job.id),
                str(job.company),
                str(job.position),
                str(job.status.value),
                str(applied_date),
                str(resume_count)
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error listing jobs: {str(e)}[/red]")

@cli.command()
@click.option('--job-id', prompt='Job ID', type=int, help='ID of the job application')
def show_resumes(job_id):
    """Show all resume versions for a job application"""
    try:
        job = storage.get_job(job_id)
        if not job:
            console.print(f"[red]No job found with ID {job_id}[/red]")
            return

        versions = storage.get_job_resume_versions(job_id)
        if not versions:
            console.print("[yellow]No resume versions found for this job[/yellow]")
            return

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Version")
        table.add_column("Filename")
        table.add_column("Upload Date")
        table.add_column("Notes")

        for version in versions:
            upload_date = getattr(version, 'upload_date', None)
            table.add_row(
                str(version.version),
                str(version.filename),
                upload_date.strftime("%Y-%m-%d %H:%M:%S") if upload_date else "N/A",
                str(getattr(version, 'notes', None)) if getattr(version, 'notes', None) else "N/A"
            )

        console.print(f"\nResumes for {job.company} - {job.position}")
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error showing resumes: {str(e)}[/red]")

@cli.command()
@click.option('--job-id', prompt='Job ID', type=int, help='ID of the job application')
@click.confirmation_option(prompt='Are you sure you want to delete this job?')
def delete_job(job_id):
    """Delete a job application and its associated resume versions"""
    try:
        job = storage.get_job(job_id)
        if not job:
            console.print(f"[red]No job found with ID {job_id}[/red]")
            return

        # Delete associated files from S3
        for version in job.resume_versions:
            s3.delete_file(version.s3_key)

        # Delete from database
        storage.delete_job(job_id)
        console.print(f"[green]Successfully deleted job application for {job.company}[/green]")
    except Exception as e:
        console.print(f"[red]Error deleting job: {str(e)}[/red]")

@cli.command()
@click.option('--keyword', prompt='Search keyword', help='Keyword to search for in emails')
@click.option('--max-results', default=50, help='Maximum number of emails to return')
@click.option('--search-subject/--no-search-subject', default=True, help='Search in email subjects')
@click.option('--search-body/--no-search-body', default=True, help='Search in email bodies')
@click.option('--search-sender/--no-search-sender', default=True, help='Search in sender addresses')
def search_emails(keyword, max_results, search_subject, search_body, search_sender):
    """Search for job-related emails using a keyword"""
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
        
        if not emails:
            console.print("[yellow]No matching emails found[/yellow]")
            return
            
        # Create table for display
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Date", style="dim")
        table.add_column("From")
        table.add_column("Subject")
        table.add_column("Content Preview")
        
        for email in emails:
            # Get preview of body (first 100 chars)
            preview = email.body[:100].replace('\n', ' ').strip()
            if len(email.body) > 100:
                preview += "..."
                
            table.add_row(
                email.date.strftime("%Y-%m-%d %H:%M"),
                email.sender,
                email.subject,
                preview
            )
            
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error searching emails: {str(e)}[/red]")

if __name__ == '__main__':
    cli() 