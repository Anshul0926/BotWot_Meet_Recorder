import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.file']
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")

def setup_google_drive_api():
    logger.info("Setting up Google Drive API authentication...")
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    logger.info("Google Drive API authentication successful.")
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(filename, drive_service):
    logger.info(f"Uploading file '{filename}' to Google Drive...")
    file_metadata = {
        'name': os.path.basename(filename),
        'parents': [DRIVE_FOLDER_ID] if DRIVE_FOLDER_ID else []
    }
    media = MediaFileUpload(filename, mimetype='text/plain')
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    logger.info(f"File uploaded successfully to Google Drive with ID: {file.get('id')}")

if __name__ == "__main__":
    # Create a dummy file for testing
    with open('test.txt', 'w') as f:
        f.write("This is a test file for Google Drive upload.")
    drive_service = setup_google_drive_api()
    upload_to_drive('test.txt', drive_service)
    os.remove('test.txt')