"""
URL Validation and Cleaning Utilities
Validates competitor links and ensures .json endpoints work
"""

import requests
from typing import Optional, Tuple, Dict, List
from urllib.parse import urlparse, urlunparse
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


class URLValidator:
    """Validates and cleans URLs, especially for Shopify product links"""

    @staticmethod
    def clean_url(url: str) -> str:
        """
        Clean and normalize a URL
        - Remove fragments and query parameters
        - Ensure proper scheme (https)
        - Remove trailing slashes
        """
        if not url or not url.strip():
            return ""

        url = url.strip()

        # Add scheme if missing
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'

        # Parse and reconstruct without query params and fragments
        parsed = urlparse(url)

        # Upgrade http to https
        scheme = 'https' if parsed.scheme == 'http' else parsed.scheme

        # Remove trailing slash from path
        path = parsed.path.rstrip('/')

        clean_url = urlunparse((
            scheme,
            parsed.netloc,
            path,
            '', '', ''  # No params, query, or fragment
        ))

        return clean_url

    @staticmethod
    def get_json_url(url: str) -> str:
        """
        Convert a product URL to its JSON endpoint
        Cleans the URL and appends .json
        """
        clean = URLValidator.clean_url(url)

        if not clean:
            return ""

        # Add .json if not present
        if not clean.endswith('.json'):
            return f"{clean}.json"

        return clean

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    def validate_json_endpoint(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that a URL returns valid JSON when .json is appended

        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        if not url or not url.strip():
            return False, "Empty URL"

        try:
            json_url = self.get_json_url(url)

            if not json_url:
                return False, "Invalid URL format"

            logger.debug(f"Testing JSON endpoint: {json_url}")

            headers = {
                'User-Agent': settings.USER_AGENT,
                'Accept': 'application/json'
            }

            response = requests.get(
                json_url,
                headers=headers,
                timeout=settings.SCRAPE_TIMEOUT,
                allow_redirects=True
            )

            # Check status code
            if response.status_code == 404:
                return False, "404 Not Found"
            elif response.status_code == 403:
                return False, "403 Forbidden"
            elif response.status_code >= 400:
                return False, f"HTTP {response.status_code}"

            # Check if response is valid JSON
            try:
                data = response.json()

                # For Shopify products, verify structure
                if '/products/' in url:
                    if 'product' not in data:
                        return False, "Invalid JSON structure (no 'product' key)"

                    product = data['product']
                    if not product.get('title'):
                        return False, "Missing product title"

                return True, None

            except ValueError as e:
                return False, f"Invalid JSON: {str(e)}"

        except requests.Timeout:
            return False, "Request timeout"
        except requests.ConnectionError:
            return False, "Connection error"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def validate_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a regular URL (not JSON endpoint)

        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        if not url or not url.strip():
            return False, "Empty URL"

        try:
            clean = self.clean_url(url)

            if not clean:
                return False, "Invalid URL format"

            logger.debug(f"Testing URL: {clean}")

            headers = {
                'User-Agent': settings.USER_AGENT
            }

            response = requests.head(
                clean,
                headers=headers,
                timeout=settings.SCRAPE_TIMEOUT,
                allow_redirects=True
            )

            if response.status_code >= 400:
                return False, f"HTTP {response.status_code}"

            return True, None

        except requests.Timeout:
            return False, "Request timeout"
        except requests.ConnectionError:
            return False, "Connection error"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def validate_competitor_links(self, item_code: str, links: Dict[str, Optional[str]]) -> Dict[str, Dict]:
        """
        Validate all competitor links for an item

        Args:
            item_code: ERPNext item code
            links: Dict with keys 'link_1', 'link_2', 'link_3'

        Returns:
            Dict with validation results for each link
        """
        results = {}

        for link_name, url in links.items():
            if not url or not url.strip():
                results[link_name] = {
                    'url': url,
                    'clean_url': '',
                    'json_url': '',
                    'is_valid': False,
                    'json_works': False,
                    'error': 'Empty URL'
                }
                continue

            clean_url = self.clean_url(url)
            json_url = self.get_json_url(url)

            # Test regular URL
            url_valid, url_error = self.validate_url(url)

            # Test JSON endpoint
            json_valid, json_error = self.validate_json_endpoint(url)

            results[link_name] = {
                'url': url,
                'clean_url': clean_url,
                'json_url': json_url,
                'is_valid': url_valid,
                'json_works': json_valid,
                'url_error': url_error,
                'json_error': json_error
            }

        return results


def format_validation_report(item_code: str, validation_results: Dict[str, Dict]) -> str:
    """
    Format validation results into a readable report

    Args:
        item_code: ERPNext item code
        validation_results: Results from validate_competitor_links

    Returns:
        Formatted report string
    """
    lines = [f"\nItem: {item_code}"]

    has_errors = False

    for link_name, result in validation_results.items():
        url = result['url']

        if not url:
            continue

        lines.append(f"\n  {link_name}:")
        lines.append(f"    Original: {url}")

        if result['clean_url'] != url:
            lines.append(f"    Cleaned:  {result['clean_url']}")

        if not result['is_valid']:
            lines.append(f"    URL Status: FAILED - {result['url_error']}")
            has_errors = True
        else:
            lines.append(f"    URL Status: OK")

        if not result['json_works']:
            lines.append(f"    JSON Endpoint: FAILED - {result['json_error']}")
            lines.append(f"    JSON URL: {result['json_url']}")
            has_errors = True
        else:
            lines.append(f"    JSON Endpoint: OK")

    if has_errors:
        lines.insert(0, "[ERROR]")
    else:
        lines.insert(0, "[OK]")

    return "\n".join(lines)
