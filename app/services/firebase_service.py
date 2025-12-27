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
                "private_key_id": "some_id_optional_usually", 
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
