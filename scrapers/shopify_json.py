import json
import requests
from typing import Optional
from urllib.parse import urlparse, urlunparse
from scrapers.base import BaseScraper, ProductData
from config.settings import settings
from tenacity import retry, stop_after_attempt, wait_exponential

class ShopifyJsonScraper(BaseScraper):
    """Scraper for Shopify stores using JSON endpoints"""
    
    def can_handle(self) -> bool:
        """All competitor links are Shopify stores"""
        return '/products/' in self.url
    
    def get_json_url(self) -> str:
        """Convert product URL to JSON endpoint"""
        # Remove any query params or fragments
        parsed = urlparse(self.url)
        clean_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip('/'),
            '', '', ''
        ))
        
        # Add .json extension if not present
        if not clean_url.endswith('.json'):
            return f"{clean_url}.json"
        return clean_url
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def scrape(self) -> Optional[ProductData]:
        """Scrape product data from Shopify JSON endpoint"""
        json_url = self.get_json_url()
        self.logger.info(f"Fetching Shopify product JSON: {json_url}")
        
        try:
            headers = {
                'User-Agent': settings.USER_AGENT,
                'Accept': 'application/json'
            }
            
            response = requests.get(
                json_url, 
                headers=headers,
                timeout=settings.SCRAPE_TIMEOUT
            )
            
            response.raise_for_status()
            data = response.json()
            
            if 'product' not in data:
                self.logger.error("Invalid JSON structure - no 'product' key")
                return None
            
            product = data['product']
            
            # Extract product name
            name = product.get('title', '')
            
            # Extract Shopify handle
            handle = product.get('handle', '')
            
            # Extract description (may contain HTML)
            description = product.get('body_html', '') or product.get('description', '')
            
            # Extract all image URLs in order (first image will be primary)
            image_urls = []
            if 'images' in product:
                # Images are already in the correct order from Shopify
                # The first image is the featured/primary image
                for img in product['images']:
                    if 'src' in img:
                        # Get the original/largest image
                        img_url = img['src']
                        # Remove any size parameters to get full resolution
                        if '?' in img_url:
                            img_url = img_url.split('?')[0]
                        image_urls.append(img_url)
            
            if not name:
                self.logger.error("No product name found")
                return None
            
            self.logger.info(f"Successfully scraped: {name} ({len(image_urls)} images)")
            
            return ProductData(
                name=name,
                description=self.clean_description(description),
                image_urls=image_urls,
                handle=handle,
                raw_data=product,
                source='shopify_json'
            )
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch JSON: {e}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON response: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return None