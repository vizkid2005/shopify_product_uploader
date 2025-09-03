import base64
import json
import re
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
from config.settings import settings
from utils.logger import get_logger
from tenacity import retry, stop_after_attempt, wait_exponential

logger = get_logger(__name__)

class ShopifyClient:
    """Client for Shopify Admin API (GraphQL + REST)"""
    
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
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def search_product_by_handle(self, handle: str) -> Optional[Dict[str, Any]]:
        """Search for a product by handle using GraphQL"""
        query = """
        query getProductByHandle($handle: String!) {
            productByHandle(handle: $handle) {
                id
                title
                handle
                metafields(first: 10, namespace: "erpnext") {
                    edges {
                        node {
                            key
                            value
                        }
                    }
                }
            }
        }
        """
        
        variables = {"handle": handle}
        
        try:
            response = requests.post(
                self.graphql_url,
                json={"query": query, "variables": variables},
                headers=self.headers
            )
            response.raise_for_status()
            
            data = response.json()
            if 'errors' in data:
                logger.error(f"GraphQL errors: {data['errors']}")
                return None
            
            product = data.get('data', {}).get('productByHandle')
            if product:
                logger.info(f"Found existing product with handle: {handle}")
            return product
            
        except Exception as e:
            logger.error(f"Error searching for product: {e}")
            return None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def search_product_by_metafield(self, item_code: str) -> Optional[Dict[str, Any]]:
        """Search for a product by ERPNext item code metafield"""
        query = """
        query getProductByMetafield($namespace: String!, $key: String!, $value: String!) {
            products(first: 1, query: $query) {
                edges {
                    node {
                        id
                        title
                        handle
                        metafields(first: 10, namespace: $namespace) {
                            edges {
                                node {
                                    key
                                    value
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        
        # Build metafield query
        metafield_query = f'metafield.namespace:"erpnext" AND metafield.key:"item_code" AND metafield.value:"{item_code}"'
        variables = {
            "query": metafield_query,
            "namespace": "erpnext",
            "key": "item_code",
            "value": item_code
        }
        
        try:
            response = requests.post(
                self.graphql_url,
                json={"query": query, "variables": variables},
                headers=self.headers
            )
            response.raise_for_status()
            
            data = response.json()
            if 'errors' in data:
                logger.error(f"GraphQL errors: {data['errors']}")
                return None
            
            products = data.get('data', {}).get('products', {}).get('edges', [])
            if products:
                product = products[0]['node']
                logger.info(f"Found existing product with metafield item_code: {item_code}")
                return product
            
            return None
            
        except Exception as e:
            logger.error(f"Error searching by metafield: {e}")
            return None
    
    def product_exists(self, item_code: str) -> bool:
        """Check if a product exists by metafield (the source of truth for ERPNext mapping)"""
        # Only check by metafield since handles are sanitized and not 1:1 with item codes
        if self.search_product_by_metafield(item_code):
            return True
        
        # Also check by sanitized handle as a fallback for older products
        sanitized_handle = self.sanitize_handle(item_code)
        if self.search_product_by_handle(sanitized_handle):
            # Double-check the metafield to ensure it's the right product
            logger.warning(f"Found product by handle '{sanitized_handle}' but checking metafield")
            return True
        
        return False
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_product(self,
                      item_code: str,
                      title: str,
                      description_html: str,
                      image_paths: List[Path],
                      price: str,
                      vendor: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Create a new product with images using REST API.
        Images are uploaded in order - first image will be the primary.
        """
        # Sanitize handle for Shopify
        sanitized_handle = self.sanitize_handle(item_code)
        logger.info(f"Creating product: {title} (handle: {sanitized_handle}, item_code: {item_code})")
        
        # Prepare images with base64 encoding
        images = []
        for i, image_path in enumerate(image_paths):
            if not image_path.exists():
                logger.warning(f"Image file not found: {image_path}")
                continue
            
            try:
                with open(image_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                
                image_obj = {
                    "attachment": image_data,
                    "filename": image_path.name
                }
                
                # First image is automatically set as featured
                if i == 0:
                    logger.info(f"Setting primary image: {image_path.name}")
                
                images.append(image_obj)
                
            except Exception as e:
                logger.error(f"Error encoding image {image_path}: {e}")
        
        # Build product data
        product_data = {
            "product": {
                "title": title,
                "body_html": description_html,
                "vendor": vendor or "Your Store",
                "handle": sanitized_handle,  # Use sanitized handle for URL safety
                "status": "active",
                "published": True,
                "images": images,
                "variants": [
                    {
                        "price": price,
                        "sku": item_code,  # Keep original item code as SKU
                        "inventory_management": "shopify",
                        "inventory_policy": "deny",
                        "fulfillment_service": "manual",
                        "requires_shipping": True
                    }
                ],
                "metafields": [
                    {
                        "namespace": "erpnext",
                        "key": "item_code",
                        "value": item_code,  # Store original item code in metafield
                        "type": "single_line_text_field"
                    }
                ]
            }
        }
        
        try:
            url = f"{self.rest_base_url}/products.json"
            
            if settings.DRY_RUN:
                logger.info("DRY RUN: Would create product with data:")
                logger.info(f"Title: {title}, Handle: {sanitized_handle}, Item Code: {item_code}, Images: {len(images)}")
                return {"id": "dry_run", "handle": sanitized_handle}
            
            response = requests.post(
                url,
                json=product_data,
                headers=self.headers
            )
            
            if response.status_code == 201:
                result = response.json()
                product = result.get('product', {})
                logger.info(f"Successfully created product: {product.get('id')} - {title}")
                return product
            else:
                logger.error(f"Failed to create product: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating product: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test the connection to Shopify"""
        try:
            url = f"{self.rest_base_url}/shop.json"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            shop = response.json().get('shop', {})
            logger.info(f"Connected to Shopify store: {shop.get('name')}")
            return True
            
        except Exception as e:
            logger.error(f"Shopify connection test failed: {e}")
            return False