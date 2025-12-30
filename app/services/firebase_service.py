import os
from datetime import datetime, timezone
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
    """Updates user usage statistics atomically, including daily tracking."""
    try:
        db = firestore.client()
        doc_ref = db.collection('users').document(str(user_id))
        
        # Ensure file_type is one of our expected categories
        allowed_types = ['photo', 'video', 'audio', 'document', 'sticker', 'voice', 'video_note']
        if file_type not in allowed_types:
            file_type = 'document'

        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        # We need to check the date for the daily reset
        doc = doc_ref.get(['usage.daily'])
        daily_usage = doc.to_dict().get('usage', {}).get('daily', {})
        
        updates = {
            "usage.total_files": firestore.Increment(1),
            "usage.total_bytes": firestore.Increment(file_size_bytes),
            f"usage.breakdown.{file_type}.count": firestore.Increment(1),
            f"usage.breakdown.{file_type}.bytes": firestore.Increment(file_size_bytes),
            "usage.last_updated": firestore.SERVER_TIMESTAMP
        }

        if daily_usage.get('date') == today:
            # Same day, just increment
            updates["usage.daily.bytes"] = firestore.Increment(file_size_bytes)
        else:
            # New day or first time, reset
            updates["usage.daily.date"] = today
            updates["usage.daily.bytes"] = file_size_bytes
        
        doc_ref.update(updates)
        logger.info(f"Updated usage stats for user {user_id} ({file_type}, {file_size_bytes} bytes)")
    except Exception as e:
        logger.error(f"Failed to update usage stats for {user_id}: {e}")

def check_usage_limit(user_id: int, file_size_bytes: int) -> tuple[bool, str]:
    """
    Checks if the user has enough allowance for the file.
    Free Limit: 100MB daily.
    Paid Allowance: Lifetime bytes purchased.
    """
    FREE_LIMIT_BYTES = 100 * 1024 * 1024 # 100 MB
    
    try:
        db = firestore.client()
        doc_ref = db.collection('users').document(str(user_id))
        doc = doc_ref.get()
        if not doc.exists:
            return False, "User not found. Please log in."
        
        data = doc.to_dict()
        usage = data.get('usage', {})
        daily = usage.get('daily', {})
        paid_allowance = usage.get('paid_allowance', 0)
        
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        daily_bytes = 0
        if daily.get('date') == today:
            daily_bytes = daily.get('bytes', 0)
        
        # Check Free Limit
        if daily_bytes + file_size_bytes <= FREE_LIMIT_BYTES:
            return True, ""
        
        # Check Paid Allowance
        # Logic: If daily limit exceeded, use paid allowance
        # We don't strictly "deduct" from paid allowance here, we track total usage vs (total daily allowance + total paid)
        # But to keep it simple: any byte above FREE_LIMIT is counted against paid_allowance.
        
        # Bytes remaining in free daily limit
        remaining_free = max(0, FREE_LIMIT_BYTES - daily_bytes)
        over_limit = file_size_bytes - remaining_free
        
        if paid_allowance >= over_limit:
            # User has enough paid allowance. We should probably decrement it now?
            # Or just track usage vs (sum of daily credits + lifetime credits).
            # To avoid complex tracking, let's actually DECREMENT paid_allowance when used.
            doc_ref.update({"usage.paid_allowance": firestore.Increment(-over_limit)})
            return True, ""
            
        return False, f"Daily limit reached (100MB). Remaining: {paid_allowance} bytes of paid top-up. 5GB Top-up available in dashboard!"
        
    except Exception as e:
        logger.error(f"Limit check failed for {user_id}: {e}")
        return True, "" # Fail open to avoid blocking users on DB errors

def update_paid_allowance(user_id: int, bytes_to_add: int):
    """Adds paid allowance to user's usage stats."""
    try:
        db = firestore.client()
        doc_ref = db.collection('users').document(str(user_id))
        doc_ref.update({"usage.paid_allowance": firestore.Increment(bytes_to_add)})
        logger.info(f"Added {bytes_to_add} bytes allowance to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to update paid allowance for {user_id}: {e}")
