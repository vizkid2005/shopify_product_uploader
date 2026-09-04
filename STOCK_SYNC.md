# Stock Synchronization

## Overview

The stock synchronization utility syncs inventory quantities from ERPNext to Shopify with a configurable buffer threshold to account for missing or outdated stock entries.

## How It Works

### Workflow

1. **Fetch Shopify Products**: Retrieves all products from Shopify with their variants, inventory levels, and metafields
2. **ERPNext Lookup**: For each product, extracts the ERPNext `item_code` from the `erpnext.item_code` metafield
3. **Stock Retrieval**: Fetches the current stock quantity from ERPNext for that item code
4. **Buffer Logic**: Applies a buffer threshold (default: 3 pieces)
   - If ERPNext stock < threshold → Set Shopify inventory to 0
   - Otherwise → Set Shopify inventory to ERPNext quantity
5. **Update Shopify**: Updates inventory levels in Shopify for all variants

### Buffer Threshold

The buffer threshold exists to prevent overselling when stock data might be:
- Missing from ERPNext
- Outdated or stale
- Subject to minor variances

**Default**: 3 pieces

**Behavior**:
- Stock ≥ 3: Sync actual quantity to Shopify
- Stock < 3: Set Shopify inventory to 0 (safer to show out of stock)

## Usage

### Basic Command

```bash
python main.py sync-stock
```

### With Custom Buffer

```bash
python main.py sync-stock --buffer 5
```

### Dry Run (Preview Changes)

```bash
python main.py sync-stock --dry-run
```

### Limit Products

```bash
python main.py sync-stock --limit 50
```

### Combined Options

```bash
python main.py sync-stock --buffer 5 --limit 100 --dry-run
```

## Command Options

| Option | Default | Description |
|--------|---------|-------------|
| `--buffer` | 3 | Stock buffer threshold. Items below this threshold are set to 0 in Shopify |
| `--limit` | None | Maximum number of products to sync (useful for testing) |
| `--dry-run` | False | Preview changes without actually updating Shopify |

## Prerequisites

### ERPNext Setup

1. Items must have stock records in ERPNext's `Bin` doctype
2. Stock is summed across all warehouses for each item

### Shopify Setup

1. Products must have the `erpnext.item_code` metafield set
2. Products without this metafield will be skipped
3. Requires `write_inventory` permission on the Shopify API token

### API Permissions

Ensure your Shopify Admin API token has the following scopes:
- `read_products`
- `read_inventory`
- `write_inventory`

## Output

The command provides a summary after completion:

```
--- Stock Sync Summary ---
Total Products: 150
Total Variants: 150
Updated: 45
Skipped: 100
Errors: 5
```

### Status Meanings

- **Updated**: Inventory was successfully updated in Shopify
- **Skipped**: Inventory already matched, no update needed
- **Errors**: Failed to update (check logs for details)

## Implementation Details

### Architecture

```
main.py (CLI)
    ↓
services/stock_sync.py (StockSyncService)
    ↓
    ├─→ clients/erpnext.py (get_item_stock_qty)
    └─→ clients/shopify/inventory.py (InventoryManager)
```

### Key Components

1. **InventoryManager** (`clients/shopify/inventory.py`)
   - Fetches products with inventory using GraphQL
   - Updates inventory quantities via `inventorySetQuantities` mutation
   - Handles pagination for large catalogs

2. **ERPNextClient** (`clients/erpnext.py`)
   - `get_item_stock_qty()`: Fetches stock from Bin doctype
   - Sums quantities across all warehouses

3. **StockSyncService** (`services/stock_sync.py`)
   - Orchestrates the sync workflow
   - Applies buffer logic
   - Provides detailed reporting

### GraphQL Queries Used

**Fetch Products with Inventory**:
```graphql
query {
  products(first: 250) {
    edges {
      node {
        id
        handle
        title
        variants {
          id
          inventoryQuantity
          inventoryItem {
            id
            inventoryLevels {
              available
              location { id name }
            }
          }
        }
        metafields(namespace: "erpnext") {
          key
          value
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
```

**Update Inventory**:
```graphql
mutation inventorySetQuantities($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) {
    inventoryAdjustmentGroup {
      changes { name delta }
    }
    userErrors { field message }
  }
}
```

## Error Handling

### Common Issues

1. **No ERPNext item_code metafield**
   - Products without the metafield are skipped
   - Warning logged for each occurrence

2. **Stock not found in ERPNext**
   - Defaults to 0 quantity in Shopify (safe default)
   - Warning logged

3. **Failed to update Shopify**
   - Logs error with product details
   - Continues with remaining products
   - Reported in final error count

### Logging

All operations are logged with details:
- `INFO`: Normal operations and updates
- `WARNING`: Skipped products, missing data
- `ERROR`: Failed updates, API errors

Check logs for detailed troubleshooting.

## Examples

### Test with Dry Run First

```bash
# Preview what would change for first 10 products
python main.py sync-stock --limit 10 --dry-run
```

Review the output, then run for real:

```bash
python main.py sync-stock --limit 10
```

### Production Sync

```bash
# Sync all products with default buffer of 3
python main.py sync-stock
```

### Conservative Sync (Higher Buffer)

```bash
# Only show items as available if stock ≥ 5
python main.py sync-stock --buffer 5
```

## Best Practices

1. **Always dry-run first** when testing or changing buffer threshold
2. **Start with small limits** to validate behavior
3. **Monitor logs** for warnings about missing metafields
4. **Schedule regular syncs** (e.g., via cron) to keep inventory current
5. **Adjust buffer threshold** based on your stock accuracy and risk tolerance

## Future Enhancements

Potential improvements:
- Support for specific location targeting (currently uses primary location)
- Webhook-based real-time sync
- Bidirectional sync (Shopify → ERPNext)
- Per-product custom buffer thresholds
- Batch size configuration for API efficiency
