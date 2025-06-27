import imaplib
import email
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union, cast, Tuple
from dataclasses import dataclass
import os
from dotenv import load_dotenv

@dataclass
class EmailMessage:
    """Data class to store email information"""
    message_id: str
    subject: str
    sender: str
    date: datetime
    body: str
    is_html: bool

class EmailManager:
    """Manages email operations including IMAP connection and email filtering"""
    
    GMAIL_CATEGORY_PATHS = [
        "Category/Updates",
        "[Gmail]/Category/Updates",
        "Updates",
        "CATEGORY_UPDATES",  # Some IMAP implementations use this format
        "category_updates"   # Some IMAP implementations use this format
    ]
    
    def __init__(self, email_address: str, password: str, imap_server: str = "imap.gmail.com"):
        """
        Initialize EmailManager with credentials
        
        Args:
            email_address: User's email address
            password: Email password or app-specific password
            imap_server: IMAP server address (defaults to Gmail)
        """
        self.email_address = email_address
        self.password = password
        self.imap_server = imap_server
        self.connection: Optional[imaplib.IMAP4_SSL] = None

    def connect(self) -> bool:
        """
        Establish IMAP connection
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Create an IMAP4 class with SSL
            self.connection = imaplib.IMAP4_SSL(self.imap_server)
            # Authenticate
            self.connection.login(self.email_address, self.password)
            return True
        except Exception as e:
            print(f"Error connecting to email server: {str(e)}")
            return False

    def disconnect(self):
        """Close the IMAP connection"""
        if self.connection:
            try:
                self.connection.close()
                self.connection.logout()
            except:
                pass

    def _parse_email_message(self, email_message: Message) -> EmailMessage:
        """
        Parse email message into EmailMessage dataclass
        
        Args:
            email_message: Raw email message
            
        Returns:
            EmailMessage: Parsed email data
        """
        # Get subject
        subject = ""
        if email_message["subject"]:
            subject_bytes, encoding = decode_header(email_message["subject"])[0]
            if isinstance(subject_bytes, bytes):
                try:
                    subject = subject_bytes.decode(encoding or 'utf-8', errors='replace')
                except (UnicodeDecodeError, LookupError):
                    subject = subject_bytes.decode('utf-8', errors='replace')
            else:
                subject = str(subject_bytes)

        # Get sender
        sender = parseaddr(email_message.get("from", ""))[1]

        # Get date
        date_str = email_message.get("date", "")
        try:
            date = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        except:
            date = datetime.now()

        # Get body
        body = ""
        is_html = False

        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        payload = cast(bytes, part.get_payload(decode=True))
                        charset = part.get_content_charset() or 'utf-8'
                        body = payload.decode(charset, errors='replace')
                        break
                    except Exception:
                        continue
                elif part.get_content_type() == "text/html" and not body:  # Only use HTML if no plain text
                    try:
                        payload = cast(bytes, part.get_payload(decode=True))
                        charset = part.get_content_charset() or 'utf-8'
                        body = payload.decode(charset, errors='replace')
                        is_html = True
                    except Exception:
                        continue
        else:
            try:
                payload = cast(bytes, email_message.get_payload(decode=True))
                charset = email_message.get_content_charset() or 'utf-8'
                body = payload.decode(charset, errors='replace')
                is_html = email_message.get_content_type() == "text/html"
            except Exception as e:
                print(f"Error decoding email body: {str(e)}")
                body = "Error: Could not decode email body"

        return EmailMessage(
            message_id=email_message["message-id"] or "",
            subject=subject,
            sender=sender,
            date=date,
            body=body,
            is_html=is_html
        )

    def search_emails(self, 
                     keyword: str, 
                     folder: str = "INBOX", 
                     max_results: int = 50,
                     search_subject: bool = True,
                     search_body: bool = True,
                     search_sender: bool = True) -> List[EmailMessage]:
        """
        Search emails based on keyword and criteria
        
        Args:
            keyword: Search term
            folder: Email folder to search (default: INBOX)
            max_results: Maximum number of results to return
            search_subject: Whether to search in email subjects
            search_body: Whether to search in email bodies
            search_sender: Whether to search in sender addresses
            
        Returns:
            List[EmailMessage]: List of matching emails
        """
        if not self.connection:
            if not self.connect():
                return []

        try:
            if not self.connection:  # Double-check after connect attempt
                return []

            # Select the mailbox
            self.connection.select(folder)
            
            # Search for all emails in the folder
            _, message_numbers = self.connection.search(None, "ALL")
            if not message_numbers:
                return []
            
            email_messages = []
            # Convert message numbers to list of integers
            message_nums = message_numbers[0].split()
            
            # Process messages in reverse order (newest first)
            for num in reversed(message_nums):
                if len(email_messages) >= max_results:
                    break
                    
                # Fetch the email message by ID
                _, msg_data = self.connection.fetch(num, "(RFC822)")
                if not msg_data or not msg_data[0] or not isinstance(msg_data[0][1], bytes):
                    continue
                    
                email_message = email.message_from_bytes(msg_data[0][1])
                
                # Parse the email
                parsed_email = self._parse_email_message(email_message)
                
                # Check if email matches search criteria
                if (search_subject and keyword.lower() in parsed_email.subject.lower()) or \
                   (search_sender and keyword.lower() in parsed_email.sender.lower()) or \
                   (search_body and keyword.lower() in parsed_email.body.lower()):
                    email_messages.append(parsed_email)
            
            return email_messages
            
        except Exception as e:
            print(f"Error searching emails: {str(e)}")
            return []
        finally:
            self.disconnect()

    def list_folders(self) -> List[str]:
        """List all available folders/labels in the email account"""
        if not self.connection:
            if not self.connect():
                return []

        try:
            _, folders = self.connection.list()
            folder_names = []
            for folder in folders:
                try:
                    # Decode folder name and extract it from the response
                    decoded = folder.decode().split('"/"')[-1].strip('" ')
                    folder_names.append(decoded)
                except:
                    continue
            return folder_names
        except Exception as e:
            print(f"Error listing folders: {str(e)}")
            return []
        finally:
            self.disconnect()

    def find_updates_folder(self) -> Optional[str]:
        """Find the correct path for the Gmail Updates category"""
        if not self.connection:
            if not self.connect():
                return None

        try:
            # Try direct selection of common paths first
            for path in self.GMAIL_CATEGORY_PATHS:
                try:
                    if self.connection and self.connection.select(f'"{path}"'):
                        return path
                except:
                    continue

            # If direct selection failed, list all folders and search
            if not self.connection:
                return None
                
            result = self.connection.list()
            if not result or len(result) != 2:
                return None
                
            _, folders_data = result
            if not folders_data:
                return None

            # Convert bytes to string and normalize folder names
            folder_list = []
            for folder_bytes in folders_data:
                if isinstance(folder_bytes, bytes):
                    try:
                        folder_str = folder_bytes.decode('utf-8', errors='ignore')
                        if 'updates' in folder_str.lower():
                            # Extract the exact folder name from the IMAP list response
                            parts = folder_str.split('"')
                            if len(parts) >= 2:
                                folder_name = parts[-2]
                                # Verify we can select this folder
                                if self.connection and self.connection.select(f'"{folder_name}"'):
                                    return folder_name
                    except:
                        continue
            
            print("Available folders:", folder_list)  # Debug information
            return None
        except Exception as e:
            print(f"Error finding Updates folder: {str(e)}")
            return None

    def list_all_folders(self) -> List[str]:
        """List all available folders in the mailbox"""
        if not self.connection:
            if not self.connect():
                return []

        try:
            if not self.connection:
                return []
                
            result = self.connection.list()
            if not result or len(result) != 2:
                return []
                
            _, folders_data = result
            if not folders_data:
                return []

            folder_list = []
            for folder_bytes in folders_data:
                if isinstance(folder_bytes, bytes):
                    try:
                        folder_str = folder_bytes.decode('utf-8', errors='ignore')
                        # Extract folder name from IMAP response
                        parts = folder_str.split('"')
                        if len(parts) >= 2:
                            folder_name = parts[-2]
                            folder_list.append(folder_name)
                    except:
                        continue

            return folder_list
        except Exception as e:
            print(f"Error listing folders: {str(e)}")
            return []

    def search_recent_linkedin(self, 
                             hours: int = 24,
                             max_results: int = 50) -> List[EmailMessage]:
        """
        Search for recent LinkedIn Job Alert emails
        
        Args:
            hours: Number of hours to look back (default: 24)
            max_results: Maximum number of results to return
            
        Returns:
            List[EmailMessage]: List of matching emails
        """
        if not self.connection:
            if not self.connect():
                return []

        try:
            if not self.connection:
                return []

            # Select [Gmail]/All Mail folder
            try:
                status, _ = self.connection.select('"[Gmail]/All Mail"')
                if status != 'OK':
                    print("Error: Could not select [Gmail]/All Mail folder")
                    return []
            except Exception as e:
                print(f"Error selecting [Gmail]/All Mail folder: {str(e)}")
                return []

            # Calculate the date range
            date_since = (datetime.now() - timedelta(hours=hours)).strftime("%d-%b-%Y")
            print(f"Searching for emails since: {date_since}")
            
            # First try with just the date and sender to see what we get
            search_criteria = f'(SINCE "{date_since}" FROM "linkedin.com")'
            try:
                status, message_numbers = self.connection.search(None, search_criteria)
                if status != 'OK':
                    print(f"Error: Initial search failed with status {status}")
                    return []
                
                if not message_numbers or not message_numbers[0]:
                    print("No LinkedIn emails found in the specified time range")
                    return []
                    
                print(f"Found {len(message_numbers[0].split())} LinkedIn emails in total")
                
            except Exception as e:
                print(f"Error with initial search: {str(e)}")
                return []

            email_messages = []
            message_nums = message_numbers[0].split()
            
            # Process messages in reverse order (newest first)
            for num in reversed(message_nums):
                if len(email_messages) >= max_results:
                    break
                    
                try:
                    # Fetch the email message by ID
                    status, msg_data = self.connection.fetch(num, "(RFC822)")
                    if status != 'OK' or not msg_data or not msg_data[0] or not isinstance(msg_data[0][1], bytes):
                        continue
                        
                    email_message = email.message_from_bytes(msg_data[0][1])
                    parsed_email = self._parse_email_message(email_message)
                    
                    # Print subject for debugging
                    print(f"Found email with subject: {parsed_email.subject}")
                    
                    # Check for job alerts with more flexible matching
                    subject_lower = parsed_email.subject.lower()
                    if "linkedin" in subject_lower and "job" in subject_lower:
                        email_messages.append(parsed_email)
                        print(f"Added job alert: {parsed_email.subject}")
                except Exception as e:
                    print(f"Error fetching message {num}: {str(e)}")
                    continue
            
            print(f"Found {len(email_messages)} job alert emails")
            return email_messages
            
        except Exception as e:
            print(f"Error searching LinkedIn emails: {str(e)}")
            return []
        finally:
            self.disconnect()

def create_email_manager(email_address: Optional[str] = None, 
                        password: Optional[str] = None) -> EmailManager:
    """
    Create an EmailManager instance using either provided credentials or environment variables
    
    Args:
        email_address: Optional email address (will use EMAIL_ADDRESS env var if not provided)
        password: Optional password (will use EMAIL_PASSWORD env var if not provided)
        
    Returns:
        EmailManager: Configured email manager instance
    """
    load_dotenv()
    
    email_addr = email_address or os.getenv("EMAIL_ADDRESS")
    pwd = password or os.getenv("EMAIL_PASSWORD")
    
    if not email_addr or not pwd:
        raise ValueError("Email address and password must be provided either as arguments or environment variables")
        
    return EmailManager(email_addr, pwd) 