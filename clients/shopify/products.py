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

        # Step 4: Publish to Online Store sales channel
        self._publish_to_online_store(product_id)

        # Step 5: Set inventory quantity to 1 for the variant
        if variants:
            variant_id = variants[0]['node']['id']
            self._set_variant_inventory(variant_id, quantity=1)

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

        # Step 4: Ensure published to Online Store sales channel
        self._publish_to_online_store(product_id)

        # Step 5: Set inventory quantity to 1 for the variant
        if variants:
            variant_id = variants[0]['node']['id']
            self._set_variant_inventory(variant_id, quantity=1)

        return product

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _publish_to_online_store(self, product_id: str) -> bool:
        """
        Publish a product to the Online Store sales channel.
        Uses productPublish mutation to make the product available on the online store.
        """
        # First, get the Online Store sales channel ID
        sales_channel_query = """
        query getOnlineStoreSalesChannel {
            publications(first: 10) {
                edges {
                    node {
                        id
                        name
                        catalog {
                            id
                            title
                        }
                    }
                }
            }
        }
        """

        result = self.graphql.execute(sales_channel_query)
        if not result:
            logger.error("Failed to get sales channels")
            return False

        publications = result.get('publications', {}).get('edges', [])
        online_store_id = None

        # Find the Online Store publication
        for pub in publications:
            pub_data = pub['node']
            if 'Online Store' in pub_data.get('name', '') or 'online' in pub_data.get('name', '').lower():
                online_store_id = pub_data['id']
                break

        if not online_store_id:
            logger.warning("Online Store sales channel not found, skipping publication")
            return False

        # Publish the product to the Online Store
        publish_mutation = """
        mutation productPublish($input: ProductPublishInput!) {
            productPublish(input: $input) {
                product {
                    id
                    status
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """

        # Prepare variables for publishing
        variables = {
            "input": {
                "id": product_id,
                "productPublications": [{
                    "publicationId": online_store_id
                }]
            }
        }

        publish_result = self.graphql.execute(publish_mutation, variables)
        if not publish_result:
            logger.error(f"Failed to publish product {product_id}")
            return False

        publish_data = publish_result.get('productPublish', {})
        if publish_data.get('userErrors'):
            logger.error(f"Product publish errors: {publish_data['userErrors']}")
            return False

        logger.info(f"Successfully published product {product_id} to Online Store")
        return True

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _set_variant_inventory(self, variant_id: str, quantity: int = 1) -> bool:
        """
        Set inventory quantity for a product variant.
        Uses inventoryAdjustQuantities mutation to set available inventory.
        """
        # First get the inventory item ID for the variant
        variant_query = """
        query getVariantInventory($id: ID!) {
            productVariant(id: $id) {
                id
                inventoryQuantity
                inventoryItem {
                    id
                    inventoryLevels(first: 1) {
                        edges {
                            node {
                                id
                                quantities(names: "available") {
                                    quantity
                                }
                                location {
                                    id
                                    name
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        result = self.graphql.execute(variant_query, {"id": variant_id})
        if not result:
            logger.error(f"Failed to get variant inventory for {variant_id}")
            return False

        variant = result.get('productVariant')
        if not variant:
            logger.error(f"Variant {variant_id} not found")
            return False

        inventory_item = variant.get('inventoryItem')
        if not inventory_item:
            logger.error(f"No inventory item found for variant {variant_id}")
            return False

        inventory_levels = inventory_item.get('inventoryLevels', {}).get('edges', [])
        if not inventory_levels:
            logger.warning(f"No inventory levels found for variant {variant_id}")
            return False

        inventory_level = inventory_levels[0]['node']
        location_id = inventory_level['location']['id']

        # Get available quantity from the new API structure
        quantities = inventory_level.get('quantities', [])
        current_available = quantities[0]['quantity'] if quantities else 0

        # Calculate the adjustment needed
        adjustment = quantity - current_available

        if adjustment == 0:
            logger.info(f"Inventory already at {quantity} for variant {variant_id}")
            return True

        # Use inventoryAdjustQuantities to set the inventory
        adjustment_mutation = """
        mutation inventoryAdjustQuantities($input: InventoryAdjustQuantitiesInput!) {
            inventoryAdjustQuantities(input: $input) {
                inventoryAdjustmentGroup {
                    createdAt
                    reason
                    changes {
                        name
                        delta
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """

        variables = {
            "input": {
                "reason": "correction",
                "name": "available",
                "changes": [{
                    "delta": adjustment,
                    "inventoryItemId": inventory_item['id'],
                    "locationId": location_id
                }]
            }
        }

        adjustment_result = self.graphql.execute(adjustment_mutation, variables)
        if not adjustment_result:
            logger.error(f"Failed to adjust inventory for variant {variant_id}")
            return False

        adjustment_data = adjustment_result.get('inventoryAdjustQuantities', {})
        if adjustment_data.get('userErrors'):
            logger.error(f"Inventory adjustment errors: {adjustment_data['userErrors']}")
            return False

        logger.info(f"Successfully set inventory to {quantity} for variant {variant_id}")
        return True