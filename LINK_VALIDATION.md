# Link Validation Utility

## Overview

The link validation utility (`utils/url_validator.py`) provides functionality to:
- Clean and normalize URLs (remove query params, fragments, trailing slashes)
- Verify URLs are accessible
- Test that `.json` endpoints return valid JSON responses
- Generate comprehensive validation reports

This is particularly useful for validating competitor product links before scraping.

## Features

### URL Cleaning
- Removes query parameters and URL fragments
- Upgrades HTTP to HTTPS
- Removes trailing slashes
- Trims whitespace

### JSON Endpoint Validation
- Appends `.json` to product URLs
- Verifies the endpoint returns valid JSON
- Checks for proper Shopify product structure
- Validates required fields (e.g., product title)

### Error Detection
- 404 Not Found
- 403 Forbidden
- Connection errors
- Timeout errors
- Invalid JSON responses
- Missing required fields

## CLI Usage

### Validate All Items

```bash
# Check all items in ERPNext
python main.py validate-links

# Check first 20 items
python main.py validate-links --limit 20

# Save detailed report to file
python main.py validate-links --save-report
```

### Validate Single Item

```bash
# Check specific item
python main.py validate-links --item-code ITEM-001 --save-report
```

## Output

The command outputs:
1. **Real-time feedback**: Shows errors and warnings as they're found
2. **Summary statistics**: Total counts of OK/warning/error items
3. **Item lists**: Lists all items with issues
4. **Optional report file**: Detailed report with all validation results

### Example Output

```
================================================================================
Validation Summary
================================================================================
Total items checked: 50
Items with all links OK: 42
Items with warnings: 5
Items with errors: 3

Warning items: ITEM-005, ITEM-012, ITEM-023, ITEM-034, ITEM-041
Error items: ITEM-007, ITEM-015, ITEM-028
```

### Report File Format

When using `--save-report`, a detailed text file is generated:

```
================================================================================
Competitor Link Validation Report
Generated: 2025-11-14T10:30:00
================================================================================

[ERROR]

Item: ITEM-007

  link_1:
    Original: https://broken-site.com/products/item
    URL Status: FAILED - 404 Not Found
    JSON Endpoint: FAILED - 404 Not Found
    JSON URL: https://broken-site.com/products/item.json

  link_2:
    Original: https://ourascents.com/products/valid-item
    URL Status: OK
    JSON Endpoint: OK

[OK]

Item: ITEM-008

  link_1:
    Original: https://ourascents.com/products/test
    URL Status: OK
    JSON Endpoint: OK

================================================================================
Summary
================================================================================
Total items checked: 50
Items with all links OK: 42
Items with warnings: 5
Items with errors: 3

Items with broken links:
  - ITEM-007
  - ITEM-015
  - ITEM-028
```

## Programmatic Usage

You can also use the validator in your own Python scripts:

```python
from utils.url_validator import URLValidator, format_validation_report

# Create validator instance
validator = URLValidator()

# Clean a URL
clean_url = validator.clean_url("https://example.com/products/item?variant=123")
# Returns: "https://example.com/products/item"

# Get JSON endpoint URL
json_url = validator.get_json_url("https://example.com/products/item")
# Returns: "https://example.com/products/item.json"

# Validate a URL
is_valid, error = validator.validate_url("https://example.com/products/item")
if not is_valid:
    print(f"URL is broken: {error}")

# Validate JSON endpoint
json_works, json_error = validator.validate_json_endpoint("https://example.com/products/item")
if not json_works:
    print(f"JSON endpoint failed: {json_error}")

# Validate all competitor links for an item
links = {
    'link_1': 'https://ourascents.com/products/perfume',
    'link_2': 'https://hamidi.ae/products/attar',
    'link_3': None
}
results = validator.validate_competitor_links("ITEM-001", links)

# Format results as a report
report = format_validation_report("ITEM-001", results)
print(report)
```

## Error Types

### URL Errors
- `Empty URL` - No URL provided
- `Invalid URL format` - Malformed URL
- `404 Not Found` - URL doesn't exist
- `403 Forbidden` - Access denied
- `HTTP XXX` - Other HTTP error
- `Request timeout` - Server didn't respond
- `Connection error` - Network issue

### JSON Endpoint Errors
- All URL errors (above)
- `Invalid JSON: <reason>` - Response is not valid JSON
- `Invalid JSON structure (no 'product' key)` - Missing expected Shopify structure
- `Missing product title` - Product data incomplete

## Filtering

The validation utility automatically excludes certain items:

- **Excluded from online stores**: Items with the `custom_exclude_from_online_stores` checkbox enabled in ERPNext are automatically skipped during validation
- **No competitor links**: Items with no competitor links defined are skipped

This ensures validation focuses only on relevant items.

## Integration with Pipeline

The validation utility integrates with the existing scraping pipeline:

1. **Before scraping**: Run `validate-links` to identify broken URLs
2. **Fix broken links**: Update competitor links in ERPNext
3. **Run scraping**: Execute `scrape` command with confidence

This prevents wasted API calls and provides early warning of data quality issues.

## Testing

Run the test suite to verify functionality:

```bash
python test_url_validator.py
```

The test suite validates:
- URL cleaning (removing params, fragments, etc.)
- JSON URL generation
- Report formatting
- Network validation (when enabled)

## Performance

- Uses retry logic (2 attempts) for network requests
- Configurable timeout (from settings)
- Progress indicators every 10 items
- Rate limiting respected (uses existing rate limiter)

## Configuration

The validator uses settings from `config/settings.py`:
- `USER_AGENT` - User agent string for requests
- `SCRAPE_TIMEOUT` - Request timeout in seconds

## Future Enhancements

Potential improvements:
- Parallel validation for faster processing
- Cache validation results to avoid re-checking
- Integration with ERPNext to auto-update broken links
- Email notifications for broken links
- Scheduled validation runs
