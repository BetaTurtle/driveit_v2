import os
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from app.config import logger
from app.services.firebase_service import get_user_credentials

def upload_file_to_drive_sync(file_obj, filename, mime_type, user_id: int):
    """
    Uploads a file object to Google Drive.
    This function is SYNCHRONOUS and blocking. It should be run in an executor.
    """
    try:
        # 1. Get Credentials
        creds_data, error_msg = get_user_credentials(user_id)
        if error_msg:
            logger.warning(f"Credential error for user {user_id}: {error_msg}")
            return False, error_msg

        # 2. Build Google Credentials
        client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
        client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
        
        google_creds = Credentials(
            token=creds_data.get('access_token'),
            refresh_token=creds_data.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=['https://www.googleapis.com/auth/drive.file']
        )

        # 3. Build Drive Service
        service = build('drive', 'v3', credentials=google_creds, cache_discovery=False)

        # 4. Upload File
        file_metadata = {'name': filename}
        media = MediaIoBaseUpload(file_obj, mimetype=mime_type, resumable=True)
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        
        logger.info(f"File uploaded ID: {file.get('id')}")
        return True, file.get('webViewLink')

    except Exception as e:
        error_str = str(e)
        if "insufficient authentication scopes" in error_str or "Insufficient Permission" in error_str:
            logger.warning(f"User {user_id} has insufficient permissions: {error_str}")
            return False, "⚠️ Permission Error: Your Google Drive connection is missing required access. Please use the Web App to Unlink and then Connect your account again."
            
        logger.error(f"Error in upload_file_to_drive: {e}")
        return False, error_str
