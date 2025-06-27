import os
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class S3Handler:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        self.bucket_name = os.getenv('AWS_BUCKET_NAME')

    def upload_file(self, file_path, job_id):
        """
        Upload a file to S3 bucket
        
        Args:
            file_path (str): Path to the file to upload
            job_id (int): Job ID to associate with the file
            
        Returns:
            str: S3 key of the uploaded file
        """
        try:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = os.path.basename(file_path)
            s3_key = f"resumes/job_{job_id}/{timestamp}_{filename}"
            
            self.s3_client.upload_file(file_path, self.bucket_name, s3_key)
            logger.info(f"Successfully uploaded {filename} to S3")
            return s3_key
        
        except ClientError as e:
            logger.error(f"Error uploading file to S3: {str(e)}")
            raise

    def download_file(self, s3_key, local_path):
        """
        Download a file from S3 bucket
        
        Args:
            s3_key (str): S3 key of the file to download
            local_path (str): Local path to save the file
        """
        try:
            # Check if file exists first
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.error(f"File {s3_key} not found in S3")
                    raise FileNotFoundError(f"File {s3_key} not found in S3")
                else:
                    raise

            # If we got here, file exists, so download it
            self.s3_client.download_file(self.bucket_name, s3_key, local_path)
            logger.info(f"Successfully downloaded {s3_key} from S3")
        
        except ClientError as e:
            logger.error(f"Error downloading file from S3: {str(e)}")
            raise

    def delete_file(self, s3_key):
        """
        Delete a file from S3 bucket
        
        Args:
            s3_key (str): S3 key of the file to delete
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"Successfully deleted {s3_key} from S3")
        
        except ClientError as e:
            logger.error(f"Error deleting file from S3: {str(e)}")
            raise 