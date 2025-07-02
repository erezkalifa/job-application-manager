import os
import shutil
from fastapi import UploadFile
from pathlib import Path
from datetime import datetime

class FileService:
    # Get the absolute path to the project root
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    UPLOAD_DIR = PROJECT_ROOT / "uploads" / "resumes"

    @classmethod
    async def save_resume(cls, file: UploadFile, job_id: int, version: int) -> tuple[str, str]:
        """
        Save a resume file to the uploads directory.
        
        Args:
            file (UploadFile): The uploaded file
            job_id (int): The ID of the job this resume is for
            version (int): The version number for this resume
            
        Returns:
            tuple[str, str]: A tuple containing (file_path, original_filename)
        """
        # Create uploads directory if it doesn't exist
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)
        
        # Get original filename and extension
        original_filename = file.filename or f"resume_{job_id}_v{version}.pdf"
        file_extension = os.path.splitext(original_filename)[1]
        
        # Create versioned filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"resume_{job_id}_v{version}_{timestamp}{file_extension}"
        file_path = cls.UPLOAD_DIR / filename
        
        try:
            # Read the uploaded file
            contents = await file.read()
            
            # Write to new file
            with open(file_path, "wb") as f:
                f.write(contents)
            
            return str(file_path), original_filename
        except Exception as e:
            print(f"Error saving file: {str(e)}")
            raise Exception(f"Could not save file: {str(e)}")
        finally:
            await file.close()

    @classmethod
    def delete_resume(cls, file_path: str) -> None:
        """
        Delete a resume file
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting file: {str(e)}")
            raise Exception(f"Could not delete file: {str(e)}") 