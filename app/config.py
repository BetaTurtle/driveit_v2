import logging
import os
import asyncio
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# Logging Configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Reduce noise from third-party libs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

logger = logging.getLogger("driveit_bot")

# Constants
LIFESPAN = 18000  # 5 Hours
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GOOGLE_SHEETS_TOKEN = os.environ.get("GOOGLE_SHEETS_TOKEN")
# Defaulting to a placeholder ID if not in env or if env value is empty
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID") or "1XmYmpHfsa3TLgsEM9qIqR_NkpVxX6iKO6Kkec0uzOzk"

# Concurrency Controls
GLOBAL_SEMAPHORE = asyncio.Semaphore(5)
USER_LOCKS = defaultdict(asyncio.Lock)
