import asyncio
import time
from io import BytesIO
from telegram import Bot, Update
from telegram.constants import ParseMode
from app.config import logger, GLOBAL_SEMAPHORE, USER_LOCKS
from app.services.drive_service import upload_file_to_drive_sync

async def handle_upload_task(bot: Bot, chat_id: int, user_id: int, message_id: int, file_data: bytes, filename: str, mime_type: str, status_msg_id: int):
    """
    Background task to handle the upload process with queueing.
    """
    try:
        # 1. Wait for User Lock (Per-user queue)
        async with USER_LOCKS[user_id]:
            
            # 2. Wait for Global Semaphore (Global concurrency limit)
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
            try:
                await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
            except Exception:
                pass 
                
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
    
    try:
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
            
    except Exception as e:
        error_msg = str(e)
        if "File is too big" in error_msg:
             await bot.send_message(
                chat_id=chat_id, 
                text="❌ This file is too large for the Telegram Bot API (Limit: 20MB).",
                reply_to_message_id=update.message.message_id
            )
             return
        logger.error(f"Error in get_file: {e}")
        return

    if file_to_download:
        # 1. Send Queued Message
        status_msg = await bot.send_message(
            chat_id=chat_id, 
            text="📥 Downloading to bot...", 
            reply_to_message_id=update.message.message_id
        )
        
        try:
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
            
            # Update status to Queued
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
