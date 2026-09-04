"""
Shopify Inventory Management
Handles inventory queries and updates using GraphQL Admin API
"""

from typing import Optional, List, Dict, Any
from utils.logger import get_logger

logger = get_logger(__name__)


class InventoryManager:
    """Manages Shopify inventory operations using GraphQL"""

    def __init__(self, graphql_executor):
        """
        Args:
            graphql_executor: GraphQLExecutor instance for executing queries
        """
        self.graphql = graphql_executor

    def get_all_products_with_inventory(self, cursor: Optional[str] = None, limit: int = 250) -> Dict[str, Any]:
        """
        Fetch all products with their inventory levels and metafields.
        Returns paginated results.

        Args:
            cursor: Pagination cursor for fetching next page
            limit: Number of products to fetch per page (max 250)

        Returns:
            Dict containing products data and pagination info:
            {
                'products': [
                    {
                        'id': 'gid://...',
                        'handle': '...',
                        'title': '...',
                        'metafields': [...],
                        'variants': [...]
                    }
                ],
                'has_next_page': bool,
                'end_cursor': str or None
            }
        """
        after_clause = f'after: "{cursor}"' if cursor else ''

        query = f"""
        query {{
          products(first: {limit}, {after_clause}) {{
            edges {{
              node {{
                id
                handle
                title
                totalInventory
                variants(first: 100) {{
                  edges {{
                    node {{
                      id
                      title
                      inventoryQuantity
                      inventoryItem {{
                        id
                      }}
                    }}
                  }}
                }}
                metafields(first: 10, namespace: "erpnext") {{
                  edges {{
                    node {{
                      key
                      value
                    }}
                  }}
                }}
              }}
              cursor
            }}
            pageInfo {{
              hasNextPage
              endCursor
            }}
          }}
        }}
        """

        try:
            data = self.graphql.execute(query)
            if not data or 'products' not in data:
                logger.error("Failed to fetch products with inventory")
                return {
                    'products': [],
                    'has_next_page': False,
                    'end_cursor': None
                }

            products_data = data['products']
            edges = products_data.get('edges', [])
            page_info = products_data.get('pageInfo', {})

            # Parse products
            products = []
            for edge in edges:
                node = edge['node']

                # Parse metafields
                metafields = {}
                for mf_edge in node.get('metafields', {}).get('edges', []):
                    mf_node = mf_edge['node']
                    metafields[mf_node['key']] = mf_node['value']

                # Parse variants with inventory
                variants = []
                for var_edge in node.get('variants', {}).get('edges', []):
                    var_node = var_edge['node']
                    inv_item = var_node.get('inventoryItem', {})

                    variants.append({
                        'id': var_node['id'],
                        'title': var_node.get('title', ''),
                        'inventory_quantity': var_node.get('inventoryQuantity', 0),
                        'inventory_item_id': inv_item.get('id')
                    })

                products.append({
                    'id': node['id'],
                    'handle': node.get('handle', ''),
                    'title': node.get('title', ''),
                    'total_inventory': node.get('totalInventory', 0),
                    'metafields': metafields,
                    'variants': variants
                })

            return {
                'products': products,
                'has_next_page': page_info.get('hasNextPage', False),
                'end_cursor': page_info.get('endCursor')
            }

        except Exception as e:
            logger.error(f"Error fetching products with inventory: {e}", exc_info=True)
            return {
                'products': [],
                'has_next_page': False,
                'end_cursor': None
            }

    def get_all_products_with_inventory_generator(self, limit: int = 250):
        """
        Generator that yields all products with inventory, handling pagination automatically.

        Args:
            limit: Number of products to fetch per page (max 250)

        Yields:
            Individual product dictionaries
        """
        cursor = None
        while True:
            result = self.get_all_products_with_inventory(cursor=cursor, limit=limit)

            products = result['products']
            if not products:
                break

            for product in products:
                yield product

            if not result['has_next_page']:
                break

            cursor = result['end_cursor']

    def update_inventory_quantity(
        self,
        inventory_item_id: str,
        location_id: str,
        quantity: int,
        reason: str = "correction"
    ) -> bool:
        """
        Update inventory quantity for a specific variant at a location.

        Args:
            inventory_item_id: Shopify inventory item ID (GID format)
            location_id: Shopify location ID (GID format)
            quantity: New quantity to set
            reason: Reason for inventory change (default: "correction")

        Returns:
            True if successful, False otherwise
        """
        mutation = """
        mutation inventorySetQuantities($input: InventorySetQuantitiesInput!) {
          inventorySetQuantities(input: $input) {
            inventoryAdjustmentGroup {
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
                "name": "available",
                "reason": reason,
                "ignoreCompareQuantity": True,
                "quantities": [
                    {
                        "inventoryItemId": inventory_item_id,
                        "locationId": location_id,
                        "quantity": quantity
                    }
                ]
            }
        }

        try:
            data = self.graphql.execute(mutation, variables)

            if not data or 'inventorySetQuantities' not in data:
                logger.error("Failed to update inventory quantity")
                return False

            result = data['inventorySetQuantities']

            # Check for user errors
            user_errors = result.get('userErrors', [])
            if user_errors:
                for error in user_errors:
                    logger.error(f"Inventory update error: {error.get('message')} (field: {error.get('field')})")
                return False

            # Log successful update
            changes = result.get('inventoryAdjustmentGroup', {}).get('changes', [])
            for change in changes:
                logger.info(f"Inventory {change.get('name')} changed by {change.get('delta')}")

            logger.info(f"Successfully updated inventory to {quantity} for item {inventory_item_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating inventory quantity: {e}", exc_info=True)
            return False

    def batch_update_inventory(
        self,
        updates: List[Dict[str, Any]],
        reason: str = "correction"
    ) -> Dict[str, Any]:
        """
        Batch update multiple inventory quantities in a single mutation.

        Args:
            updates: List of dicts with keys: inventory_item_id, location_id, quantity
            reason: Reason for inventory changes

        Returns:
            Dict with success/failure counts and errors
        """
        if not updates:
            return {'success': 0, 'failed': 0, 'errors': []}

        mutation = """
        mutation inventorySetQuantities($input: InventorySetQuantitiesInput!) {
          inventorySetQuantities(input: $input) {
            inventoryAdjustmentGroup {
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

        quantities = []
        for update in updates:
            quantities.append({
                "inventoryItemId": update['inventory_item_id'],
                "locationId": update['location_id'],
                "quantity": update['quantity']
            })

        variables = {
            "input": {
                "name": "available",
                "reason": reason,
                "ignoreCompareQuantity": True,
                "quantities": quantities
            }
        }

        try:
            data = self.graphql.execute(mutation, variables)

            if not data or 'inventorySetQuantities' not in data:
                logger.error("Failed to batch update inventory")
                return {
                    'success': 0,
                    'failed': len(updates),
                    'errors': ['GraphQL execution failed']
                }

            result = data['inventorySetQuantities']

            # Check for user errors
            user_errors = result.get('userErrors', [])
            if user_errors:
                error_messages = [f"{err.get('message')} (field: {err.get('field')})" for err in user_errors]
                logger.error(f"Batch inventory update errors: {error_messages}")
                return {
                    'success': 0,
                    'failed': len(updates),
                    'errors': error_messages
                }

            # Log successful updates
            changes = result.get('inventoryAdjustmentGroup', {}).get('changes', [])
            logger.info(f"Successfully updated {len(changes)} inventory items")

            return {
                'success': len(updates),
                'failed': 0,
                'errors': []
            }

        except Exception as e:
            logger.error(f"Error in batch inventory update: {e}", exc_info=True)
            return {
                'success': 0,
                'failed': len(updates),
                'errors': [str(e)]
            }
