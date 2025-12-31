import asyncio
import time
import contextlib
from telegram import Bot, Update
from telegram.error import Forbidden, NetworkError

from app.config import logger, LIFESPAN, TELEGRAM_BOT_TOKEN
from app.services.firebase_service import init_firebase
from app.bot_handlers import process_update
from app.services.sheet_service import SheetContext

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

    try:
        async with Bot(TELEGRAM_BOT_TOKEN) as bot:
            logger.info("Listening for new messages...")
            background_tasks = set()
            
            while True:
                # Check lifespan
                if time.time() - start_time > LIFESPAN:
                    logger.info("Lifespan reached. Waiting for pending tasks...")
                    if background_tasks:
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
                    
                    break

                try:
                    updates = await bot.get_updates(
                        offset=update_id, 
                        timeout=10, 
                        allowed_updates=Update.ALL_TYPES
                    )
                    
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
    except asyncio.CancelledError:
        logger.info("Main task cancelled. Shutting down...")
        # Optional: flush if cancelled?
        # await sheet_context.flush() 
        raise
    finally:
        # Stop the executor
        sheet_context.shutdown()

if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
