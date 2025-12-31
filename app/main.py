import asyncio
import time
import contextlib
from telegram import Bot, Update
from telegram.error import Forbidden, NetworkError

from app.config import logger, LIFESPAN, TELEGRAM_BOT_TOKEN
from app.services.firebase_service import init_firebase
from app.bot_handlers import process_update
from app.services.sheet_service import SheetContext

from telegram.request import HTTPXRequest

import signal

async def main():
    """Run the bot."""
    init_firebase()
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in env")
        return

    update_id = None 
    logger.info("Starting bot...")
    start_time = time.time()
    
    # Initialize Sheet Context
    sheet_context = SheetContext()
    
    # Robust request configuration for CI/CD environments
    request = HTTPXRequest(connection_pool_size=8, connect_timeout=30.0, read_timeout=30.0)

    # Signal Handling for Graceful Shutdown (GitHub Actions sends SIGTERM)
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_sigterm():
        logger.info("Received SIGTERM. Initiating graceful shutdown...")
        stop_event.set()

    loop.add_signal_handler(signal.SIGTERM, handle_sigterm)

    try:
        # Retry loop for initial connection
        async with Bot(TELEGRAM_BOT_TOKEN, request=request) as bot:
            logger.info("Listening for new messages...")
            background_tasks = set()
            
            while not stop_event.is_set():
                # Check lifespan
                if time.time() - start_time > LIFESPAN:
                    logger.info("Lifespan reached. Initiating shutdown...")
                    break
                
                try:
                    # Use a short timeout for get_updates to check stop_event frequently
                    # Or better: use wait_for with the stop_event
                    get_updates_task = asyncio.create_task(bot.get_updates(
                        offset=update_id, 
                        timeout=10, 
                        allowed_updates=Update.ALL_TYPES
                    ))
                    
                    done, pending = await asyncio.wait(
                        [get_updates_task, stop_event.wait()], 
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    if stop_event.is_set():
                        # If stopped, cancel the pending get_updates
                        get_updates_task.cancel()
                        break
                    
                    # If we got updates
                    updates = await get_updates_task
                    
                    for update in updates:
                        update_id = update.update_id + 1
                        
                        # Track update for sheets
                        sheet_context.add_update(update)
                        if sheet_context.should_flush():
                            await sheet_context.flush()

                        task = asyncio.create_task(process_update(bot, update))
                        background_tasks.add(task)
                        task.add_done_callback(background_tasks.discard)

                except NetworkError:
                    await asyncio.sleep(1)
                except Forbidden:
                    if update_id is not None:
                         update_id += 1
                except Exception as e:
                    logger.error(f"Unexpected error: {e}")
                    await asyncio.sleep(5)
            
            # --- SHUTDOWN SEQUENCE ---
            logger.info("Waiting for pending tasks...")
            if background_tasks:
                 # Wait for all background tasks to complete
                 await asyncio.gather(*background_tasks, return_exceptions=True)
            
            # Flush pending sheet updates
            logger.info("Flushing pending sheet updates...")
            await sheet_context.flush(blocking=True)

            logger.info("All tasks finished. Exiting...")
            
            # Final Ack
            if update_id is not None:
                try:
                    await bot.get_updates(offset=update_id, timeout=0, limit=1)
                    logger.info(f"Successfully acked updates up to {update_id}")
                except Exception as e:
                    logger.error(f"Failed to perform final ack: {e}")

    except asyncio.CancelledError:
        logger.info("Main task cancelled.")
        raise
    finally:
        sheet_context.shutdown()

if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
