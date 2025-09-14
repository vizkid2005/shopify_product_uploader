from pathlib import Path
from typing import Optional, List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import settings
from utils.logger import get_logger
from .graphql import GraphQLExecutor
from .media import MediaManager
from .base import ShopifyBase

logger = get_logger(__name__)

class ProductManager:
    """Handles product-related operations including search, creation, and updates"""
    
    def __init__(self, graphql_executor: GraphQLExecutor, media_manager: MediaManager):
        self.graphql = graphql_executor
        self.media = media_manager
        # Lazy import to avoid circular dependency
        self._validation = None
    
    @property 
    def validation(self):
        """Lazy load validation to avoid circular import"""
        if self._validation is None:
            from .validation import ShopifyValidation
            self._validation = ShopifyValidation(self.graphql)
        return self._validation
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def search_by_handle(self, handle: str) -> Optional[Dict[str, Any]]:
        """Search for a product by handle using GraphQL"""
        query = """
        query getProductByHandle($handle: String!) {
            productByHandle(handle: $handle) {
                id
                title
                handle
                status
                vendor
                descriptionHtml
                variants(first: 1) {
                    edges {
                        node {
                            id
                            price
                            sku
                        }
                    }
                }
                media(first: 10) {
                    edges {
                        node {
                            id
                            alt
                            mediaContentType
                        }
                    }
                }
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
        result = self.graphql.execute(query, variables)
        
        if not result:
            return None
        
        product = result.get('productByHandle')
        if product:
            logger.info(f"Found existing product with handle: {handle}")
        return product
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def search_by_metafield(self, item_code: str) -> Optional[Dict[str, Any]]:
        """Search for a product by ERPNext item code metafield"""
        query = """
        query getProductByMetafield($query: String!) {
            products(first: 1, query: $query) {
                edges {
                    node {
                        id
                        title
                        handle
                        status
                        vendor
                        descriptionHtml
                        variants(first: 1) {
                            edges {
                                node {
                                    id
                                    price
                                    sku
                                }
                            }
                        }
                        media(first: 10) {
                            edges {
                                node {
                                    id
                                    alt
                                    mediaContentType
                                }
                            }
                        }
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
            }
        }
        """
        
        # Build metafield query - search for products with specific metafield value
        metafield_query = f'metafields.namespace:erpnext AND metafields.key:item_code AND metafields.value:"{item_code}"'
        variables = {"query": metafield_query}
        
        result = self.graphql.execute(query, variables)
        if not result:
            return None
        
        products = result.get('products', {}).get('edges', [])
        if products:
            product = products[0]['node']
            logger.info(f"Found existing product with metafield item_code: {item_code}")
            return product
        
        return None
    
    def exists(self, handle: str, item_code: str) -> bool:
        """Check if a product exists by handle or metafield"""
        # First check by handle (primary method)
        if self.search_by_handle(handle):
            return True
        
        # Also check by metafield as fallback
        if self.search_by_metafield(item_code):
            return True
        
        return False
    
    def get_existing(self, handle: str, item_code: str) -> Optional[Dict[str, Any]]:
        """Get existing product data by handle or metafield"""
        # First check by handle (primary method)
        product = self.search_by_handle(handle)
        if product:
            return product
        
        # Also check by metafield as fallback (commented out in original)
        # product = self.search_by_metafield(item_code)
        # if product:
        #     return product
        
        return None
    
    def get_shopify_id(self, handle: str, item_code: str) -> Optional[str]:
        """
        Get the Shopify product ID (numeric) for a product by handle or metafield.
        Returns the numeric ID, not the GID.
        """
        product = self.get_existing(handle, item_code)
        if product and product.get('id'):
            return product.get('id')
        return None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create(self,
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
        # Sanitize the provided handle for Shopify
        sanitized_handle = ShopifyBase.sanitize_handle(handle)
        logger.info(f"Creating product: {title} (handle: {sanitized_handle}, item_code: {item_code})")
        
        # Ensure required metafield definitions exist
        validation_result = self.validation.ensure_required_setup()
        if not validation_result.get("success"):
            logger.error(f"Shopify setup validation failed: {validation_result.get('errors', [])}")
            return None
        
        if settings.DRY_RUN:
            logger.info("DRY RUN: Would create product with data:")
            logger.info(f"Title: {title}, Handle: {sanitized_handle}, Item Code: {item_code}, Images: {len(image_paths)}")
            if seo_title:
                logger.info(f"SEO Title: {seo_title}")
            if meta_description:
                logger.info(f"Meta Description: {meta_description}")
            return {"id": "gid://shopify/Product/dry_run", "handle": sanitized_handle}
        
        # Step 1: Create the product using GraphQL
        mutation = """
        mutation productCreate($product: ProductCreateInput!) {
            productCreate(product: $product) {
                product {
                    id
                    title
                    handle
                    status
                    variants(first: 1) {
                        edges {
                            node {
                                id
                                price
                                sku
                            }
                        }
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        
        # Build metafields
        metafields = [{
            "namespace": "erpnext",
            "key": "item_code",
            "value": item_code,
            "type": "single_line_text_field"
        }]
        
        # Build SEO fields
        seo = {}
        if seo_title:
            seo["title"] = seo_title
        if meta_description:
            seo["description"] = meta_description
        
        product_input = {
            "title": title,
            "descriptionHtml": description_html,
            "vendor": vendor or "Your Store",
            "handle": sanitized_handle,
            "status": "ACTIVE",
            "metafields": metafields
        }
        
        if seo:
            product_input["seo"] = seo
        
        # Validate product data before creating
        product_validation = self.validation.validate_product_fields(product_input)
        if not product_validation.get("success"):
            logger.error(f"Product validation failed: {product_validation.get('errors', [])}")
            return None
        
        # Log any warnings
        for warning in product_validation.get("warnings", []):
            logger.warning(warning)
        
        variables = {"product": product_input}
        
        result = self.graphql.execute(mutation, variables)
        if not result:
            logger.error("Failed to execute product creation GraphQL")
            return None
        
        product_create_result = result.get('productCreate', {})
        if product_create_result.get('userErrors'):
            logger.error(f"Product creation errors: {product_create_result['userErrors']}")
            return None
        
        product = product_create_result.get('product')
        if not product:
            logger.error("Product creation succeeded but no product returned")
            return None
        
        product_id = product.get('id')
        logger.info(f"Successfully created product: {product_id} - {title}")
        
        # Step 2: Update the variant with price and SKU
        variants = product.get('variants', {}).get('edges', [])
        if variants:
            variant_id = variants[0]['node']['id']
            self._update_variant_price_and_sku(variant_id, price, item_code)
        
        # Step 3: Upload media if provided
        if image_paths:
            media_objects = self.media.upload_product_media(product_id, image_paths)
            logger.info(f"Uploaded {len(media_objects)} media files for product")
        
        return product

    def _update_variant_price_and_sku(self, variant_id: str, price: str, sku: str) -> bool:
        """
        Update a product variant with price and SKU using GraphQL.
        Uses productVariantsBulkUpdate for both price and SKU.
        """
        # Extract product ID from variant ID (gid://shopify/ProductVariant/123 -> we need the product ID)
        # We need to get the product ID from the variant first
        query = """
        query getVariantProduct($id: ID!) {
            productVariant(id: $id) {
                id
                product {
                    id
                }
            }
        }
        """

        variant_result = self.graphql.execute(query, {"id": variant_id})
        if not variant_result or not variant_result.get('productVariant'):
            logger.error(f"Failed to get product ID for variant {variant_id}")
            return False

        product_id = variant_result['productVariant']['product']['id']

        # Use productVariantsBulkUpdate for both price and SKU
        mutation = """
        mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
            productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                product {
                    id
                }
                productVariants {
                    id
                    price
                    sku
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """

        # Validate variant data - include price and use barcode field for SKU in ProductVariantsBulkInput
        variant_data = {
            "id": variant_id,
            "price": price,
            "barcode": sku,  # Use barcode field instead of sku which doesn't exist in ProductVariantsBulkInput
            "inventoryPolicy": "DENY"
        }

        variant_validation = self.validation.validate_variant_fields(variant_data)
        if not variant_validation.get("success"):
            logger.error(f"Variant validation failed: {variant_validation.get('errors', [])}")
            return False

        # Log any warnings
        for warning in variant_validation.get("warnings", []):
            logger.warning(warning)

        variables = {
            "productId": product_id,
            "variants": [variant_data]
        }

        result = self.graphql.execute(mutation, variables)
        if not result:
            return False

        update_result = result.get('productVariantsBulkUpdate', {})
        if update_result.get('userErrors'):
            logger.error(f"Variant update errors: {update_result['userErrors']}")
            return False

        logger.info(f"Successfully updated variant {variant_id} with price {price} and barcode {sku}")
        return True
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def update(self,
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
        sanitized_handle = ShopifyBase.sanitize_handle(handle)
        logger.info(f"Updating product {product_id}: {title} (handle: {sanitized_handle}, item_code: {item_code})")
        
        # Ensure required metafield definitions exist
        validation_result = self.validation.ensure_required_setup()
        if not validation_result.get("success"):
            logger.error(f"Shopify setup validation failed: {validation_result.get('errors', [])}")
            return None
        
        if settings.DRY_RUN:
            logger.info("DRY RUN: Would update product with data:")
            logger.info(f"Title: {title}, Handle: {sanitized_handle}, Item Code: {item_code}, Images: {len(image_paths)}")
            if seo_title:
                logger.info(f"SEO Title: {seo_title}")
            if meta_description:
                logger.info(f"Meta Description: {meta_description}")
            return {"id": product_id, "handle": sanitized_handle}
        
        # Step 1: Update product details using GraphQL
        mutation = """
        mutation productUpdate($input: ProductInput!) {
            productUpdate(input: $input) {
                product {
                    id
                    title
                    handle
                    status
                    variants(first: 1) {
                        edges {
                            node {
                                id
                                price
                                sku
                            }
                        }
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        
        # Build SEO fields
        seo = {}
        if seo_title:
            seo["title"] = seo_title
        if meta_description:
            seo["description"] = meta_description
        
        product_input = {
            "id": product_id,
            "title": title,
            "descriptionHtml": description_html,
            "vendor": vendor or "Your Store",
            "handle": sanitized_handle,
            "status": "ACTIVE"
        }
        
        if seo:
            product_input["seo"] = seo
        
        # Validate product data before updating
        product_validation = self.validation.validate_product_fields(product_input)
        if not product_validation.get("success"):
            logger.error(f"Product validation failed: {product_validation.get('errors', [])}")
            return None
        
        # Log any warnings
        for warning in product_validation.get("warnings", []):
            logger.warning(warning)
        
        variables = {
            "input": product_input
        }
        
        result = self.graphql.execute(mutation, variables)
        if not result:
            logger.error("Failed to execute product update GraphQL")
            return None
        
        product_update_result = result.get('productUpdate', {})
        if product_update_result.get('userErrors'):
            logger.error(f"Product update errors: {product_update_result['userErrors']}")
            return None
        
        product = product_update_result.get('product')
        if not product:
            logger.error("Product update succeeded but no product returned")
            return None
        
        logger.info(f"Successfully updated product details: {product_id} - {title}")
        
        # Step 2: Update the variant with price and SKU
        variants = product.get('variants', {}).get('edges', [])
        if variants:
            variant_id = variants[0]['node']['id']
            self._update_variant_price_and_sku(variant_id, price, item_code)
        
        # Step 3: Replace media if provided
        if image_paths:
            # Delete existing media first
            self.media.delete_existing_media(product_id)
            
            # Upload new media
            media_objects = self.media.upload_product_media(product_id, image_paths)
            logger.info(f"Replaced with {len(media_objects)} new media files for product")
        
        return product