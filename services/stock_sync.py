"""
Stock Synchronization Service
Syncs inventory from ERPNext to Shopify with buffer logic
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from utils.logger import get_logger
from clients.erpnext import ERPNextClient
from clients.shopify import ShopifyClient

logger = get_logger(__name__)


@dataclass
class StockSyncResult:
    """Result of a stock sync operation"""
    product_id: str
    product_title: str
    item_code: Optional[str]
    erpnext_qty: Optional[float]
    shopify_qty: int
    new_qty: int
    updated: bool
    error: Optional[str] = None


class StockSyncService:
    """
    Service for synchronizing stock from ERPNext to Shopify.

    Workflow:
    1. Fetch all products from Shopify with their metafields
    2. For each product, look up the ERPNext item_code from metafield
    3. Fetch stock quantity from ERPNext
    4. Apply buffer logic: if ERPNext stock < 3, set Shopify to 0
    5. Update Shopify inventory if different
    """

    def __init__(
        self,
        erpnext_client: ERPNextClient,
        shopify_client: ShopifyClient,
        buffer_threshold: int = 3,
        dry_run: bool = False
    ):
        """
        Args:
            erpnext_client: ERPNext client instance
            shopify_client: Shopify client instance
            buffer_threshold: Minimum stock level before setting to 0 in Shopify (default: 3)
            dry_run: If True, don't actually update inventory
        """
        self.erpnext = erpnext_client
        self.shopify = shopify_client
        self.buffer_threshold = buffer_threshold
        self.dry_run = dry_run

        # Initialize inventory manager from Shopify client
        self.inventory_manager = shopify_client.graphql
        # We'll need to create the InventoryManager instance
        from clients.shopify.inventory import InventoryManager
        self.inventory = InventoryManager(self.inventory_manager)

    def calculate_shopify_quantity(self, erpnext_qty: Optional[float]) -> int:
        """
        Calculate the Shopify quantity based on ERPNext quantity and buffer logic.

        Args:
            erpnext_qty: Quantity from ERPNext (can be None if not found)

        Returns:
            Quantity to set in Shopify
        """
        if erpnext_qty is None:
            # If we can't get ERPNext stock, set to 0 for safety
            logger.warning("ERPNext quantity not available, setting Shopify to 0")
            return 0

        if erpnext_qty < self.buffer_threshold:
            # Below threshold, set to 0 in Shopify
            logger.info(f"ERPNext quantity {erpnext_qty} < threshold {self.buffer_threshold}, setting to 0")
            return 0

        # Otherwise, use the ERPNext quantity (rounded down to int)
        return int(erpnext_qty)

    def sync_product_stock(
        self,
        product: Dict[str, Any],
        location_id: str
    ) -> List[StockSyncResult]:
        """
        Sync stock for a single product.

        Args:
            product: Product data from Shopify including variants and metafields
            location_id: Shopify location ID to update inventory at

        Returns:
            List of StockSyncResult, one per variant
        """
        results = []

        product_id = product['id']
        product_title = product['title']
        metafields = product.get('metafields', {})

        # Get ERPNext item_code from metafield
        item_code = metafields.get('item_code')

        if not item_code:
            logger.warning(f"Product {product_title} ({product_id}) has no ERPNext item_code metafield, skipping")
            results.append(StockSyncResult(
                product_id=product_id,
                product_title=product_title,
                item_code=None,
                erpnext_qty=None,
                shopify_qty=0,
                new_qty=0,
                updated=False,
                error="No ERPNext item_code metafield"
            ))
            return results

        # Fetch stock from ERPNext
        erpnext_qty = self.erpnext.get_item_stock_qty(item_code)

        # Calculate target Shopify quantity with buffer logic
        target_qty = self.calculate_shopify_quantity(erpnext_qty)

        # Process each variant
        variants = product.get('variants', [])
        for variant in variants:
            variant_id = variant['id']
            inventory_item_id = variant.get('inventory_item_id')

            if not inventory_item_id:
                logger.warning(f"Variant {variant_id} has no inventory_item_id, skipping")
                results.append(StockSyncResult(
                    product_id=product_id,
                    product_title=f"{product_title} - {variant.get('title', 'Default')}",
                    item_code=item_code,
                    erpnext_qty=erpnext_qty,
                    shopify_qty=variant.get('inventory_quantity', 0),
                    new_qty=target_qty,
                    updated=False,
                    error="No inventory_item_id"
                ))
                continue

            # Get current Shopify quantity
            current_qty = variant.get('inventory_quantity', 0)

            # Check if update is needed
            if current_qty == target_qty:
                logger.info(f"Variant {variant_id} already at target quantity {target_qty}, skipping")
                results.append(StockSyncResult(
                    product_id=product_id,
                    product_title=f"{product_title} - {variant.get('title', 'Default')}",
                    item_code=item_code,
                    erpnext_qty=erpnext_qty,
                    shopify_qty=current_qty,
                    new_qty=target_qty,
                    updated=False
                ))
                continue

            # Update inventory
            if self.dry_run:
                logger.info(
                    f"DRY RUN: Would update {product_title} ({item_code}) from {current_qty} to {target_qty}"
                )
                results.append(StockSyncResult(
                    product_id=product_id,
                    product_title=f"{product_title} - {variant.get('title', 'Default')}",
                    item_code=item_code,
                    erpnext_qty=erpnext_qty,
                    shopify_qty=current_qty,
                    new_qty=target_qty,
                    updated=True
                ))
            else:
                success = self.inventory.update_inventory_quantity(
                    inventory_item_id=inventory_item_id,
                    location_id=location_id,
                    quantity=target_qty,
                    reason="correction"
                )

                if success:
                    logger.info(
                        f"Updated {product_title} ({item_code}) from {current_qty} to {target_qty}"
                    )
                    results.append(StockSyncResult(
                        product_id=product_id,
                        product_title=f"{product_title} - {variant.get('title', 'Default')}",
                        item_code=item_code,
                        erpnext_qty=erpnext_qty,
                        shopify_qty=current_qty,
                        new_qty=target_qty,
                        updated=True
                    ))
                else:
                    logger.error(f"Failed to update inventory for {product_title} ({item_code})")
                    results.append(StockSyncResult(
                        product_id=product_id,
                        product_title=f"{product_title} - {variant.get('title', 'Default')}",
                        item_code=item_code,
                        erpnext_qty=erpnext_qty,
                        shopify_qty=current_qty,
                        new_qty=target_qty,
                        updated=False,
                        error="Failed to update Shopify inventory"
                    ))

        return results

    def sync_all_stock(self, location_id: str, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Sync stock for all products in Shopify.

        Args:
            location_id: Shopify location ID to update inventory at
            limit: Optional limit on number of products to process

        Returns:
            Summary dict with statistics
        """
        logger.info(f"Starting stock sync (buffer threshold: {self.buffer_threshold}, dry_run: {self.dry_run})")

        total_products = 0
        total_variants = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        results = []

        try:
            # Fetch all products with inventory (use smaller page size to avoid GraphQL cost limit)
            for product in self.inventory.get_all_products_with_inventory_generator(limit=50):
                if limit and total_products >= limit:
                    logger.info(f"Reached limit of {limit} products")
                    break

                total_products += 1
                logger.info(f"Processing product {total_products}: {product['title']}")

                # Sync stock for this product
                product_results = self.sync_product_stock(product, location_id)
                results.extend(product_results)

                # Update counters
                total_variants += len(product_results)
                for result in product_results:
                    if result.updated:
                        updated_count += 1
                    elif result.error:
                        error_count += 1
                    else:
                        skipped_count += 1

            summary = {
                'total_products': total_products,
                'total_variants': total_variants,
                'updated': updated_count,
                'skipped': skipped_count,
                'errors': error_count,
                'dry_run': self.dry_run,
                'buffer_threshold': self.buffer_threshold,
                'results': results
            }

            logger.info(
                f"Stock sync complete: {total_products} products, "
                f"{total_variants} variants, {updated_count} updated, "
                f"{skipped_count} skipped, {error_count} errors"
            )

            return summary

        except Exception as e:
            logger.error(f"Fatal error during stock sync: {e}", exc_info=True)
            return {
                'total_products': total_products,
                'total_variants': total_variants,
                'updated': updated_count,
                'skipped': skipped_count,
                'errors': error_count + 1,
                'dry_run': self.dry_run,
                'buffer_threshold': self.buffer_threshold,
                'results': results,
                'fatal_error': str(e)
            }

    def get_primary_location_id(self) -> Optional[str]:
        """
        Get the primary location ID from Shopify.

        Returns:
            Location ID (GID format) or None if error
        """
        query = """
        query {
          locations(first: 1) {
            edges {
              node {
                id
                name
                isPrimary
              }
            }
          }
        }
        """

        try:
            data = self.inventory_manager.execute(query)
            if not data or 'locations' not in data:
                logger.error("Failed to fetch locations")
                return None

            edges = data['locations'].get('edges', [])
            if not edges:
                logger.error("No locations found in Shopify")
                return None

            location = edges[0]['node']
            location_id = location['id']
            location_name = location['name']

            logger.info(f"Using location: {location_name} ({location_id})")
            return location_id

        except Exception as e:
            logger.error(f"Error fetching primary location: {e}", exc_info=True)
            return None
