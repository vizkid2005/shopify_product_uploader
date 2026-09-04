#!/usr/bin/env python3
"""
Quick test script for URL validator functionality
"""

from utils.url_validator import URLValidator, format_validation_report

def test_url_cleaning():
    """Test URL cleaning functionality"""
    validator = URLValidator()

    test_cases = [
        # (input, expected)
        ("https://ourascents.com/products/test-product?variant=123",
         "https://ourascents.com/products/test-product"),

        ("http://hamidi.ae/products/perfume/",
         "https://hamidi.ae/products/perfume"),

        ("hamidi.us/products/attar#reviews",
         "https://hamidi.us/products/attar"),

        ("  https://example.com/products/item  ",
         "https://example.com/products/item"),
    ]

    print("Testing URL Cleaning:")
    print("=" * 80)

    for input_url, expected in test_cases:
        result = validator.clean_url(input_url)
        status = "✓" if result == expected else "✗"
        print(f"{status} Input:    {input_url}")
        print(f"  Expected: {expected}")
        print(f"  Got:      {result}")
        print()

def test_json_url_generation():
    """Test JSON URL generation"""
    validator = URLValidator()

    test_cases = [
        ("https://ourascents.com/products/test-product",
         "https://ourascents.com/products/test-product.json"),

        ("https://hamidi.ae/products/perfume/",
         "https://hamidi.ae/products/perfume.json"),

        ("https://example.com/products/item.json",
         "https://example.com/products/item.json"),
    ]

    print("\nTesting JSON URL Generation:")
    print("=" * 80)

    for input_url, expected in test_cases:
        result = validator.get_json_url(input_url)
        status = "✓" if result == expected else "✗"
        print(f"{status} Input:    {input_url}")
        print(f"  Expected: {expected}")
        print(f"  Got:      {result}")
        print()

def test_validation_with_real_urls():
    """Test validation with some example URLs (requires network)"""
    validator = URLValidator()

    # Test with a known good Shopify URL (if you have one)
    test_urls = [
        "https://ourascents.com/products/example",  # This may or may not exist
        "https://invalid-domain-xyz-123.com/products/test",  # Should fail
    ]

    print("\nTesting URL Validation (requires network):")
    print("=" * 80)
    print("Note: These tests may fail if domains are not reachable")
    print()

    for url in test_urls:
        print(f"Testing: {url}")

        # Test basic URL validation
        is_valid, error = validator.validate_url(url)
        print(f"  URL Valid: {is_valid}")
        if error:
            print(f"  URL Error: {error}")

        # Test JSON endpoint
        json_valid, json_error = validator.validate_json_endpoint(url)
        print(f"  JSON Valid: {json_valid}")
        if json_error:
            print(f"  JSON Error: {json_error}")

        print()

def test_format_report():
    """Test report formatting"""
    print("\nTesting Report Formatting:")
    print("=" * 80)

    # Mock validation results
    validation_results = {
        'link_1': {
            'url': 'https://ourascents.com/products/test',
            'clean_url': 'https://ourascents.com/products/test',
            'json_url': 'https://ourascents.com/products/test.json',
            'is_valid': True,
            'json_works': True,
            'url_error': None,
            'json_error': None
        },
        'link_2': {
            'url': 'https://broken-link.com/products/item',
            'clean_url': 'https://broken-link.com/products/item',
            'json_url': 'https://broken-link.com/products/item.json',
            'is_valid': False,
            'json_works': False,
            'url_error': '404 Not Found',
            'json_error': '404 Not Found'
        },
        'link_3': {
            'url': None,
            'clean_url': '',
            'json_url': '',
            'is_valid': False,
            'json_works': False,
            'error': 'Empty URL'
        }
    }

    report = format_validation_report("TEST-ITEM-001", validation_results)
    print(report)

if __name__ == "__main__":
    print("URL Validator Test Suite")
    print("=" * 80)
    print()

    # Run offline tests
    test_url_cleaning()
    test_json_url_generation()
    test_format_report()

    # Skip network tests in automated runs
    print("\nSkipping network tests (run manually with live URLs to test)")

    print("\n" + "=" * 80)
    print("Tests complete!")
