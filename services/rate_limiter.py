import time
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

class RateLimiter:
    """Simple rate limiter - just sleeps between requests"""
    
    def __init__(self):
        # Simple delay between requests in seconds
        self.delay = 1.0 / settings.RATE_LIMIT_RPS
        logger.info(f"Rate limiter: {self.delay:.2f} seconds between requests")
    
    def wait(self):
        """Simple sleep to rate limit"""
        time.sleep(self.delay)