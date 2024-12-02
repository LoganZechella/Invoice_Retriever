import os
import base64
import schedule
import time
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Google API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/drive.file'
]

# Google Drive folder ID where invoices will be uploaded
DRIVE_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')

def get_google_service(service_name, version, creds=None):
    """Initialize and return a Google API service."""
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
    
    return build(service_name, version, credentials=creds)

def process_emails():
    """Search for and process emails with invoice attachments from specific senders."""
    try:
        gmail_service = get_google_service('gmail', 'v1')
        drive_service = get_google_service('drive', 'v3')
        
        # Search query for specific senders and invoice-related subjects
        # Adding 'newer:1d' to only get emails from the last day
        query = """
            newer:1d
            AND
            (from:billing@render.com OR 
             from:support@netlify.com OR
             from:billing@netlify.com OR
             from:payments-noreply@google.com OR
             from:billing@webflow.com OR
             from:billing@box.com OR
             from:billing@typeform.com OR
             from:no-reply@business.amazon.com OR
             from:*@anthemwelderssupply.com)
            AND 
            (subject:invoice OR subject:receipt OR subject:bill OR subject:payment)
            AND 
            has:attachment
        """.replace('\n', ' ').strip()
        
        results = gmail_service.users().messages().list(
            userId='me', q=query
        ).execute()
        
        messages = results.get('messages', [])
        for message in messages:
            process_single_email(gmail_service, drive_service, message['id'])
            
    except Exception as e:
        logger.error(f"Error processing emails: {str(e)}")

def process_single_email(gmail_service, drive_service, msg_id):
    """Process a single email and its attachments."""
    try:
        # Get email content
        message = gmail_service.users().messages().get(
            userId='me', id=msg_id
        ).execute()
        
        # Process attachments
        if 'payload' in message and 'parts' in message['payload']:
            for part in message['payload']['parts']:
                if part.get('filename') and part['filename'].lower().endswith('.pdf'):
                    process_attachment(gmail_service, drive_service, msg_id, part)
                    
    except Exception as e:
        logger.error(f"Error processing message {msg_id}: {str(e)}")

def process_attachment(gmail_service, drive_service, msg_id, part):
    """Download and upload a single attachment."""
    try:
        if 'body' in part and 'attachmentId' in part['body']:
            attachment = gmail_service.users().messages().attachments().get(
                userId='me', messageId=msg_id, id=part['body']['attachmentId']
            ).execute()
            
            file_data = base64.urlsafe_b64decode(attachment['data'])
            filename = part['filename']
            
            # Save temporarily
            with open(f"invoices/{filename}", 'wb') as f:
                f.write(file_data)
            
            # Upload to Drive
            upload_to_drive(drive_service, filename)
            
            # Clean up
            os.remove(f"invoices/{filename}")
            
    except Exception as e:
        logger.error(f"Error processing attachment: {str(e)}")

def upload_to_drive(drive_service, filename):
    """Upload a file to Google Drive."""
    try:
        file_metadata = {
            'name': filename,
            'parents': [DRIVE_FOLDER_ID]
        }
        
        media = MediaFileUpload(
            f"invoices/{filename}",
            mimetype='application/pdf',
            resumable=True
        )
        
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        logger.info(f"File {filename} uploaded successfully, ID: {file.get('id')}")
        
    except Exception as e:
        logger.error(f"Error uploading to Drive: {str(e)}")

def main():
    """Main function to run the invoice processing job."""
    logger.info("Starting invoice processing job")
    
    # Create invoices directory if it doesn't exist
    os.makedirs('invoices', exist_ok=True)
    
    # Process emails
    process_emails()
    
    logger.info("Completed invoice processing job")

if __name__ == "__main__":
    # Schedule the job to run daily at 8:00 AM
    schedule.every().day.at("08:00").do(main)
    
    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(60)
