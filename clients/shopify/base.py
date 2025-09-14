import re
from typing import Optional
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

class ShopifyBase:
    """Base class for Shopify API operations with common utilities and configuration"""
    
    def __init__(self, store: Optional[str] = None, 
                 token: Optional[str] = None,
                 api_version: Optional[str] = None):
        self.store = store or settings.SHOPIFY_STORE
        self.token = token or settings.SHOPIFY_ADMIN_TOKEN
        self.api_version = api_version or settings.SHOPIFY_API_VERSION
        
        if not all([self.store, self.token]):
            raise ValueError("Shopify credentials not configured")
        
        self.headers = {
            'X-Shopify-Access-Token': self.token,
            'Content-Type': 'application/json'
        }
        
        self.rest_base_url = f"https://{self.store}/admin/api/{self.api_version}"
        self.graphql_url = f"{self.rest_base_url}/graphql.json"
        
        logger.info(f"Initialized Shopify client for store: {self.store}")
    
    @staticmethod
    def sanitize_handle(item_code: str) -> str:
        """
        Convert item code to a valid Shopify handle.
        Handles must be lowercase, alphanumeric with hyphens only.
        """
        # Convert to lowercase
        handle = item_code.lower()
        
        # Replace spaces and underscores with hyphens
        handle = re.sub(r'[\s_]+', '-', handle)
        
        # Remove any character that's not alphanumeric or hyphen
        handle = re.sub(r'[^a-z0-9-]', '', handle)
        
        # Remove multiple consecutive hyphens
        handle = re.sub(r'-+', '-', handle)
        
        # Remove leading/trailing hyphens
        handle = handle.strip('-')
        
        # If handle is empty after sanitization, use a fallback
        if not handle:
            handle = 'product'
        
        logger.debug(f"Sanitized handle: '{item_code}' -> '{handle}'")
        return handle
    
    @staticmethod
    def extract_id_from_gid(gid: str) -> str:
        """
        Extract the numeric ID from a Shopify GraphQL Global ID (GID).
        Example: 'gid://shopify/Product/123456' -> '123456'
        """
        if not gid:
            return ''
        
        # Split by '/' and get the last part
        parts = gid.split('/')
        if len(parts) >= 3:
            return parts[-1]
        
        return gid