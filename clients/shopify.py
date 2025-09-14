# Import the refactored client
from .shopify.client import ShopifyClient

# Keep existing imports for backward compatibility
__all__ = ['ShopifyClient']