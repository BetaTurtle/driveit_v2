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
LIFESPAN = 3600  # 1 Hour
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Concurrency Controls
GLOBAL_SEMAPHORE = asyncio.Semaphore(5)
USER_LOCKS = defaultdict(asyncio.Lock)
