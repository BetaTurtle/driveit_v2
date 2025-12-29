import os
import firebase_admin
from firebase_admin import credentials, firestore
from app.config import logger

def init_firebase():
    """Initializes Firebase Admin SDK using credentials from env."""
    try:
        if not firebase_admin._apps:
            # Construct the certificate dictionary from env vars
            private_key = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PRIVATE_KEY")
            if private_key:
                private_key = private_key.replace('\\n', '\n')
            
            cred_dict = {
                "type": "service_account",
                "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
                "private_key": private_key,
                "client_email": os.environ.get("FIREBASE_SERVICE_ACCOUNT_EMAIL"),
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            
            # Simple check if critical parts are present
            if not cred_dict["private_key"] or not cred_dict["client_email"]:
                 logger.error("Missing Firebase credentials in .env")
                 return

            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")

def get_user_credentials(user_id: int):
    """Fetches user credentials from Firestore."""
    try:
        db = firestore.client()
        doc_ref = db.collection('users').document(str(user_id))
        doc = doc_ref.get()
        
        if not doc.exists:
            return None, "You are not logged in. Please start the bot and log in via the Web App."
            
        data = doc.to_dict()
        creds_data = data.get('credentials')
        if not creds_data:
             return None, "No Google Drive credentials found. Please link your account."
             
        return creds_data, None
    except Exception as e:
        logger.error(f"Firestore error for user {user_id}: {e}")
        return None, f"Database error: {e}"

def update_user_credentials(user_id: int, new_creds: dict):
    """Updates user credentials in Firestore."""
    try:
        db = firestore.client()
        doc_ref = db.collection('users').document(str(user_id))
        doc_ref.set({'credentials': new_creds}, merge=True)
        logger.info(f"Updated refreshed credentials for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to update credentials for user {user_id}: {e}")

def update_usage_stats(user_id: int, file_type: str, file_size_bytes: int):
    """Updates user usage statistics atomically."""
    try:
        db = firestore.client()
        doc_ref = db.collection('users').document(str(user_id))
        
        # Ensure file_type is one of our expected categories
        allowed_types = ['photo', 'video', 'audio', 'document', 'sticker', 'voice', 'video_note']
        if file_type not in allowed_types:
            file_type = 'document'

        updates = {
            "usage.total_files": firestore.Increment(1),
            "usage.total_bytes": firestore.Increment(file_size_bytes),
            f"usage.breakdown.{file_type}.count": firestore.Increment(1),
            f"usage.breakdown.{file_type}.bytes": firestore.Increment(file_size_bytes),
            "usage.last_updated": firestore.SERVER_TIMESTAMP
        }
        
        doc_ref.update(updates)
        logger.info(f"Updated usage stats for user {user_id} ({file_type}, {file_size_bytes} bytes)")
    except Exception as e:
        logger.error(f"Failed to update usage stats for {user_id}: {e}")
