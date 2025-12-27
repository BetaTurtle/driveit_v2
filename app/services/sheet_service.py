import json
import logging
import asyncio
from zoneinfo import ZoneInfo
from telegram import Update
from concurrent.futures import ThreadPoolExecutor
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import GOOGLE_SHEETS_TOKEN, GOOGLE_SHEET_ID

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def get_ist_time(dt):
    """Convert UTC datetime to IST string."""
    if dt:
        return dt.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    return ""

def upload_to_sheets(row_data):
    """
    Upload a list of rows to Google Sheets.
    This is a blocking function intended to be run in an executor.
    """
    if not GOOGLE_SHEETS_TOKEN:
        logger.warning("GOOGLE_SHEETS_TOKEN not set. Skipping upload.")
        return

    try:
        # Load credentials from JSON string
        creds_dict = json.loads(GOOGLE_SHEETS_TOKEN)
        creds = Credentials.from_authorized_user_info(creds_dict, SCOPES)
        
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        
        service = build('sheets', 'v4', credentials=creds)
        body = {'values': row_data}
        sheet = service.spreadsheets()
        
        result = sheet.values().append(
            spreadsheetId=GOOGLE_SHEET_ID,
            range='Sheet1', 
            valueInputOption="RAW", 
            body=body
        ).execute()
        
        logger.info(f"Uploaded {len(row_data)} rows to sheets. Result: {result.get('updates')}")
    except Exception as e:
        logger.error(f"Failed to upload to sheets: {e}")

class SheetContext:
    def __init__(self, limit=10):
        self.buffer = []
        self.limit = limit
        # Use a dedicated executor to manage upload threads independently of the asyncio loop's default executor.
        # This allows us to explicitly shut it down.
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SheetUploader")

    def add_update(self, update: Update):
        """Extract data from update and add to buffer."""
        msg = update.effective_message
        user = update.effective_user
        
        if not msg:
            return

        text = msg.text or msg.caption or ""
        
        row = [
            get_ist_time(msg.date),
            str(msg.chat_id) if msg.chat_id else "",
            user.first_name if user else "",
            user.username if user else "",
            text,
            str(msg.message_id),
            "message" if update.message else ("edited_message" if update.edited_message else "other"),
            update.to_json()
        ]
        self.buffer.append(row)

    def should_flush(self):
        return len(self.buffer) >= self.limit

    async def flush(self, blocking=False):
        """
        Flush the buffer to Google Sheets.
        If blocking is False, schedule the upload in the background and return immediately.
        If blocking is True, await the upload.
        """
        if not self.buffer:
            return
            
        # Snapshot and clear buffer immediately to prevent double flushing
        data_to_upload = list(self.buffer)
        self.buffer.clear()
        
        loop = asyncio.get_running_loop()
        
        async def _upload():
            try:
                # Use our dedicated executor
                await loop.run_in_executor(self.executor, upload_to_sheets, data_to_upload)
            except Exception as e:
                logger.error(f"Error during async flush: {e}")

        if blocking:
            await _upload()
        else:
            # Fire and forget (or rather, track as a background task if handy, but here just spawn it)
            # We don't store the task reference here assuming errors are logged. 
            # In a robust system we might want to track these to wait on shutdown.
            asyncio.create_task(_upload())

    def shutdown(self):
        """Shutdown the executor, waiting for pending uploads."""
        logger.info("Shutting down sheet uploader executor...")
        # wait=True ensures pending futures (uploads) complete before returning
        self.executor.shutdown(wait=True)
        logger.info("Sheet uploader executor shutdown complete.")
