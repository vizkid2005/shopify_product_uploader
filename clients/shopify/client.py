from pathlib import Path
from typing import Optional, List, Dict, Any
from utils.logger import get_logger
from .base import ShopifyBase
from .graphql import GraphQLExecutor
from .media import MediaManager
from .products import ProductManager
from .verification import APIVerification
from .validation import ShopifyValidation

logger = get_logger(__name__)

class ShopifyClient(ShopifyBase):
    """Main Shopify client that orchestrates all Shopify operations"""
    
    def __init__(self, store: Optional[str] = None, 
                 token: Optional[str] = None,
                 api_version: Optional[str] = None):
        super().__init__(store, token, api_version)
        
        # Initialize components
        self.graphql = GraphQLExecutor(self.graphql_url, self.headers)
        self.media = MediaManager(self.graphql)
        self.products = ProductManager(self.graphql, self.media)
        self.verification = APIVerification(self.graphql, self.api_version, self.graphql_url, self.store)
        self.validation = ShopifyValidation(self.graphql)
        
        # Note: GraphQL verification can be performed manually using verify_graphql_access()
        # Automatic verification on init is disabled to allow graceful handling of connection issues
    
    # Product operations - delegate to ProductManager
    def search_product_by_handle(self, handle: str) -> Optional[Dict[str, Any]]:
        """Search for a product by handle using GraphQL"""
        return self.products.search_by_handle(handle)
    
    def search_product_by_metafield(self, item_code: str) -> Optional[Dict[str, Any]]:
        """Search for a product by ERPNext item code metafield"""
        return self.products.search_by_metafield(item_code)
    
    def product_exists(self, handle: str, item_code: str) -> bool:
        """Check if a product exists by handle or metafield"""
        return self.products.exists(handle, item_code)
    
    def get_existing_product(self, handle: str, item_code: str) -> Optional[Dict[str, Any]]:
        """Get existing product data by handle or metafield"""
        return self.products.get_existing(handle, item_code)
    
    def get_product_shopify_id(self, handle: str, item_code: str) -> Optional[str]:
        """
        Get the Shopify product ID (numeric) for a product by handle or metafield.
        Returns the numeric ID, not the GID.
        """
        return self.products.get_shopify_id(handle, item_code)
    
    def create_product(self,
                      item_code: str,
                      title: str,
                      description_html: str,
                      image_paths: List[Path],
                      price: str,
                      handle: str,
                      seo_title: Optional[str] = None,
                      meta_description: Optional[str] = None,
                      vendor: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Create a new product with images using GraphQL Admin API.
        Uses proper staged upload workflow for media.
        """
        return self.products.create(
            item_code=item_code,
            title=title,
            description_html=description_html,
            image_paths=image_paths,
            price=price,
            handle=handle,
            seo_title=seo_title,
            meta_description=meta_description,
            vendor=vendor
        )
    
    def update_product(self,
                      product_id: str,
                      item_code: str,
                      title: str,
                      description_html: str,
                      image_paths: List[Path],
                      price: str,
                      handle: str,
                      seo_title: Optional[str] = None,
                      meta_description: Optional[str] = None,
                      vendor: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Update an existing product in Shopify using GraphQL.
        Images are replaced - existing images are deleted and new ones uploaded.
        """
        return self.products.update(
            product_id=product_id,
            item_code=item_code,
            title=title,
            description_html=description_html,
            image_paths=image_paths,
            price=price,
            handle=handle,
            seo_title=seo_title,
            meta_description=meta_description,
            vendor=vendor
        )
    
    # Verification methods - delegate to APIVerification
    def verify_graphql_access(self) -> Dict[str, Any]:
        """
        Verify GraphQL API access and required permissions.
        Returns detailed verification results including permissions and API limits.
        """
        return self.verification.verify_access()
    
    def test_connection(self) -> bool:
        """Test the connection to Shopify using GraphQL (legacy method)"""
        return self.verification.test_connection()
    
    def verify_access_or_raise(self) -> None:
        """
        Verify GraphQL access and raise exceptions if there are critical issues.
        Use this method when you want to fail fast on connection/permission problems.
        """
        return self.verification.verify_or_raise()
    
    # Validation methods - delegate to ShopifyValidation
    def ensure_required_setup(self) -> Dict[str, Any]:
        """
        Ensure all required metafield definitions and custom fields exist.
        Should be called before creating/updating products.
        """
        return self.validation.ensure_required_setup()
    
    def validate_product_fields(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate product fields before creation/update"""
        return self.validation.validate_product_fields(product_data)
    
    # Direct access to GraphQL executor for custom operations
    def _execute_graphql(self, query: str, variables: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Execute a GraphQL query against Shopify Admin API"""
        return self.graphql.execute(query, variables)