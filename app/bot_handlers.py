import asyncio
import time
import json
import math
from io import BytesIO
from telegram import Bot, Update
from telegram.constants import ParseMode
from app.config import logger, GLOBAL_SEMAPHORE, USER_LOCKS
from app.services.drive_service import upload_file_to_drive_sync
from app.services.firebase_service import update_usage_stats, check_usage_limit, update_paid_allowance

async def handle_upload_task(bot: Bot, chat_id: int, user_id: int, message_id: int, file_data: bytes, filename: str, mime_type: str, file_type: str, status_msg_id: int):
    """
    Background task to handle the upload process with queueing.
    """
    try:
        async with USER_LOCKS[user_id]:
            
            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=status_msg_id, 
                text="Queued... (Waiting for easy traffic slot)"
            )
            
            async with GLOBAL_SEMAPHORE:
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
                
        if success:
             # Update usage stats
            asyncio.create_task(
                 asyncio.to_thread(update_usage_stats, user_id, file_type, len(file_data))
            )

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

def extract_file_info(message):
    """Extract file object, filename, and mime_type from a message."""
    file_to_download = None
    filename = "unknown_file"
    filename = "unknown_file"
    mime_type = "application/octet-stream"
    file_type_category = "document"

    if message.sticker:
        sticker = message.sticker
        file_to_download = sticker
        filename = f"sticker_{int(time.time())}.webp"
        mime_type = "image/webp"
        file_type_category = "sticker" # Explicit sticker category
        
    elif message.voice:
        voice = message.voice
        file_to_download = voice
        filename = f"voice_{int(time.time())}.ogg"
        mime_type = "audio/ogg" 
        file_type_category = "voice" # Explicit voice category

    elif message.video_note:
        vnote = message.video_note
        file_to_download = vnote
        filename = f"video_note_{int(time.time())}.mp4"
        mime_type = "video/mp4"
        file_type_category = "video_note" # Explicit video_note category

    elif message.document:
        doc = message.document
        file_to_download = doc
        filename = doc.file_name or "document"
        mime_type = doc.mime_type or mime_type
        
    elif message.photo:
        photo = message.photo[-1] # Largest size
        file_to_download = photo
        filename = f"photo_{int(time.time())}.jpg"
        mime_type = "image/jpeg"
        file_type_category = "photo"
        
    elif message.video:
        video = message.video
        file_to_download = video
        filename = video.file_name or f"video_{int(time.time())}.mp4"
        mime_type = video.mime_type or mime_type
        file_type_category = "video"

    elif message.audio:
        audio = message.audio
        file_to_download = audio
        filename = audio.file_name or f"audio_{int(time.time())}.mp3"
        mime_type = audio.mime_type or mime_type
        file_type_category = "audio"
    
    return file_to_download, filename, mime_type, file_type_category

async def process_update(bot: Bot, update: Update):
    """Process a single update."""
    # 1. Handle Pre-Checkout Query (Stars Payment)
    if update.pre_checkout_query:
        await bot.answer_pre_checkout_query(update.pre_checkout_query.id, ok=True)
        return

    # 2. Handle Successful Payment (Stars Fulfillment)
    if update.message and update.message.successful_payment:
        payment = update.message.successful_payment
        try:
            payload = json.loads(payment.invoice_payload)
            user_id = int(payload.get("user_id"))
            gb = float(payload.get("gb"))
            bytes_to_add = int(gb * 1024 * 1024 * 1024)
            
            # Construct payment info for logging
            payment_info = {
                'charge_id': payment.telegram_payment_charge_id,
                'amount': payment.total_amount,
                'currency': payment.currency,
                'gb': gb,
                # Note: 'stars' is not directly in successful_payment, but total_amount is the price in stars (if currency is XTR)
                'stars': payment.total_amount if payment.currency == 'XTR' else 0
            }
            
            # Credit the user & log transaction
            update_paid_allowance(user_id, bytes_to_add, payment_info)
            
            # Helper for readable size
            def human_readable_size(size_bytes):
                if size_bytes == 0:
                    return "0 B"
                size_name = ("B", "KB", "MB", "GB", "TB")
                i = int(math.floor(math.log(size_bytes, 1024)))
                p = math.pow(1024, i)
                s = round(size_bytes / p, 2)
                return f"{s} {size_name[i]}"

            readable_amount = human_readable_size(bytes_to_add)

            await bot.send_message(
                chat_id=update.message.chat_id,
                text=f"✨ **Purchase Confirmed!**\n\nAdded **{readable_amount}** of lifetime upload allowance to your account.\n\nThank you for supporting DriveIt! 🚀\n\nRef: `{payment.telegram_payment_charge_id}`",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Payment fulfillment failed for user {update.message.from_user.id}: {e}")
            await bot.send_message(
                chat_id=update.message.chat_id,
                text="❌ Payment was successful, but there was an error updating your allowance. Please contact support."
            )
        return

    if not update.message:
        return

    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    # Handle /start
    if update.message.text and update.message.text.startswith("/start"):
        await bot.send_message(
            chat_id=chat_id,
            text="Welcome! Send or forward me any file, and I will upload it to your Google Drive.\n\nTo connect your account: t.me/DriveItBot/manage"
        )
        return

    # Handle Files
    file_info = extract_file_info(update.message)
    file_obj, filename, mime_type, file_type = file_info

    if file_obj:
        # Check Usage Limit
        can_upload, limit_msg = check_usage_limit(user_id, file_obj.file_size)
        if not can_upload:
            # Send message with a link to top-up
            await bot.send_message(
                chat_id=chat_id, 
                text=f"❌ {limit_msg}",
                reply_to_message_id=update.message.message_id
            )
            return

    file_to_download = None
    
    try:
        if file_obj:
            file_to_download = await file_obj.get_file()
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
        status_msg = await bot.send_message(
            chat_id=chat_id, 
            text="📥 Downloading to bot...", 
            reply_to_message_id=update.message.message_id
        )
        
        try:
            f_byte_array = await file_to_download.download_as_bytearray()
            
            asyncio.create_task(
                handle_upload_task(
                    bot, 
                    chat_id, 
                    user_id, 
                    update.message.message_id, 
                    f_byte_array,
                    filename, 
                    mime_type, 
                    file_type,
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
            text="Forward a file to upload to Google Drive.\n\nTo manage your account: t.me/DriveItBot/manage"
        )
