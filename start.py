
import asyncio
import contextlib
import json
import logging
import os
import time
from typing import NoReturn, Optional
from io import BytesIO
from collections import defaultdict
from functools import partial

from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, NetworkError

# Firebase and Google Drive imports
import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# Configuration
LIFESPAN = 3600  # Run for 1 hour then exit to let the next job pick up
# Concurrency Controls
GLOBAL_SEMAPHORE = asyncio.Semaphore(5)
USER_LOCKS = defaultdict(asyncio.Lock)

# Function to initialize Firebase
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


# In-memory cache for user credentials: {user_id: (creds_data, timestamp)}
USER_CREDENTIALS_CACHE = {}
CACHE_TTL = 300  # 5 minutes

def upload_file_to_drive_sync(file_obj, filename, mime_type, user_id: int):
    """
    Uploads a file object to Google Drive.
    This function is SYNCHRONOUS and blocking. It should be run in an executor.
    """
    try:
        current_time = time.time()
        creds_data = None
        
        # 1. Check Cache
        if user_id in USER_CREDENTIALS_CACHE:
            cached_creds, timestamp = USER_CREDENTIALS_CACHE[user_id]
            if current_time - timestamp < CACHE_TTL:
                creds_data = cached_creds
                # logger.info(f"Using cached credentials for user {user_id}") # Optional logging

        # 2. Fetch from Firebase if not cached
        if not creds_data:
            db = firestore.client()
            doc_ref = db.collection('users').document(str(user_id))
            doc = doc_ref.get()
            
            if not doc.exists:
                logger.warning(f"No credentials found for user {user_id}")
                return False, "You are not logged in. Please start the bot and log in via the Web App."
                
            data = doc.to_dict()
            creds_data = data.get('credentials')
            
            if creds_data:
                # Update Cache
                USER_CREDENTIALS_CACHE[user_id] = (creds_data, current_time)
        
        if not creds_data:
             return False, "No Google Drive credentials found. Please link your account."

        # 3. Build Google Credentials
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

        # 4. Build Drive Service
        # Note: cache_discovery=False prevents some pickling issues in threads/processes sometimes, 
        # specifically around the FileCache.
        service = build('drive', 'v3', credentials=google_creds, cache_discovery=False)

        # 5. Upload File
        file_metadata = {'name': filename}
        media = MediaIoBaseUpload(file_obj, mimetype=mime_type, resumable=True)
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        
        logger.info(f"File uploaded ID: {file.get('id')}")
        return True, file.get('webViewLink')


    except Exception as e:
        logger.error(f"Error in upload_file_to_drive: {e}")
        return False, str(e)


async def handle_upload_task(bot: Bot, chat_id: int, user_id: int, message_id: int, file_data: bytes, filename: str, mime_type: str, status_msg_id: int):
    """
    Background task to handle the upload process with queueing.
    """
    try:
        # 1. Wait for User Lock (Per-user queue)
        # We check queue position roughly
        async with USER_LOCKS[user_id]:
            
            # 2. Wait for Global Semaphore (Global concurrency limit)
            # Update status to indicate waiting for slot
            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=status_msg_id, 
                text="Queued... (Waiting for easy traffic slot)"
            )
            
            async with GLOBAL_SEMAPHORE:
                # 3. Uploading
                await bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=status_msg_id, 
                    text="Uploading... 🚀"
                )
                
                # Run synchronous upload in thread pool
                loop = asyncio.get_running_loop()
                # Create a fresh BytesIO for the thread
                f_io = BytesIO(file_data)
                
                success, result = await loop.run_in_executor(
                    None, 
                    upload_file_to_drive_sync, 
                    f_io, 
                    filename, 
                    mime_type, 
                    user_id
                )
                
        # 4. Post-Upload (Outside locks)
        if success:
            # Delete status message
            try:
                await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
            except Exception:
                pass # Triggered if msg too old or deleted
                
            # Reply to original message
            await bot.send_message(
                chat_id=chat_id,
                text=f"✅ Upload Complete!\n[View in Drive]({result})",
                reply_to_message_id=message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Upload success for user {user_id}")
            
        else:
            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=status_msg_id, 
                text=f"❌ Upload Failed: {result}"
            )

    except Exception as e:
        logger.error(f"Critical error in background task: {e}")
        try:
             await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=status_msg_id, 
                text="❌ unexpected error occurred during upload."
            )
        except:
            pass


async def process_update(bot: Bot, update: Update):
    """Process a single update."""
    if not update.message:
        return

    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    # Handle /start
    if update.message.text and update.message.text.startswith("/start"):
        await bot.send_message(
            chat_id=chat_id,
            text="Welcome! Send or forward me any file, and I will upload it to your Google Drive."
        )
        return

    # Handle Files
    file_to_download = None
    filename = "unknown_file"
    mime_type = "application/octet-stream"
    
    if update.message.document:
        doc = update.message.document
        file_to_download = await doc.get_file()
        filename = doc.file_name or "document"
        mime_type = doc.mime_type or mime_type
        
    elif update.message.photo:
        photo = update.message.photo[-1] # Largest size
        file_to_download = await photo.get_file()
        filename = f"photo_{int(time.time())}.jpg"
        mime_type = "image/jpeg"
        
    elif update.message.video:
        video = update.message.video
        file_to_download = await video.get_file()
        filename = video.file_name or f"video_{int(time.time())}.mp4"
        mime_type = video.mime_type or mime_type

    elif update.message.audio:
        audio = update.message.audio
        file_to_download = await audio.get_file()
        filename = audio.file_name or f"audio_{int(time.time())}.mp3"
        mime_type = audio.mime_type or mime_type

    if file_to_download:
        # 1. Send Queued Message
        status_msg = await bot.send_message(
            chat_id=chat_id, 
            text="📥 Downloading to bot...", 
            reply_to_message_id=update.message.message_id
        )
        
        try:
            # Download file to memory (Non-blocking enough for small files, blocking for large... 
            # ideally this should also be streamed or backgrounded if very large, 
            # but standard practice for bot API usually allows await download.)
            # If download is slow, it blocks THIS update, but not other updates processed in parallel branches? 
            # No, 'await' yields control. but 'process_update' is awaited in main loop sequentially?
            # Creating a task for download + upload is better if we want to be truly non-blocking.
            
            # Let's Move EVERYTHING to background task, including download?
            # Problem: `get_file` returns a File object bound to the bot session? No, it's a simple object.
            # But the actual download might take time.
            
            # For this step, I'll await download to keep it simple and ensure we have data before queuing upload.
            # (Users asked for upload queuing).
            
            f_byte_array = await file_to_download.download_as_bytearray()
            
            # 2. Spawn Background Task
            asyncio.create_task(
                handle_upload_task(
                    bot, 
                    chat_id, 
                    user_id, 
                    update.message.message_id, 
                    f_byte_array,
                    filename, 
                    mime_type, 
                    status_msg.message_id
                )
            )
            
            # Update status to Queued immediately after download
            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=status_msg.message_id, 
                text="⏳ Queued for upload..."
            )
            
        except Exception as e:
            logger.error(f"Error processing file download: {e}")
            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="Error fetching file.")
        return

    # Handle other Text
    if update.message.text:
        await bot.send_message(
            chat_id=chat_id,
            text="Forward a file to upload to Google Drive."
        )


async def main() -> NoReturn:
    """Run the bot."""
    # Initialize Firebase first
    init_firebase()
    
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set in env")
        return

    # We don't strictly need to store update_id personally if we ack it correctly with Telegram.
    # Telegram keeps track of unconfirmed updates if we start with no offset (or 0).
    update_id = None 
    
    logger.info("Starting bot...")

    start_time = time.time()
    
    async with Bot(token) as bot:
        logger.info("Listening for new messages...")
        
        while True:
            # Check lifespan
            if time.time() - start_time > LIFESPAN:
                logger.info("Lifespan reached. Performing final cleanup to Ack updates...")
                
                # "Commit" the offset to Telegram so the next runner starts clean.
                if update_id is not None:
                    try:
                        # timeout=0 to make it a quick check/ack
                        await bot.get_updates(offset=update_id, timeout=0, limit=1)
                        logger.info(f"Successfully acked updates up to {update_id}")
                    except Exception as e:
                        logger.error(f"Failed to perform final ack: {e}")
                
                break

            try:
                # Polling
                updates = await bot.get_updates(
                    offset=update_id, 
                    timeout=10, 
                    allowed_updates=Update.ALL_TYPES
                )
                
                for update in updates:
                    update_id = update.update_id + 1
                    # Spawn task for processing update so we don't block loop
                    # We use create_task to allow parallel processing (e.g. concurrent downloads)
                    asyncio.create_task(process_update(bot, update))

            
            except NetworkError:
                await asyncio.sleep(1)
            except Forbidden:
                # The user has removed or blocked the bot.
                if update_id is not None:
                     update_id += 1
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                await asyncio.sleep(5)



if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())