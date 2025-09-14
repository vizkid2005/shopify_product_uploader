"""
Naseem-specific scraper for extracting fragrance descriptions
"""

import requests
import re
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from utils.logger import get_logger
from .base import BaseScraper, ProductData

logger = get_logger(__name__)

class NaseemScraper(BaseScraper):
    """Specialized scraper for Naseem perfume websites"""
    
    SUPPORTED_DOMAINS = [
        'naseem.com',
        'canada.naseem.com', 
        'naseemperfume.in'
    ]
    
    def __init__(self, url: str):
        super().__init__(url)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def can_handle(self) -> bool:
        """Check if this scraper can handle the URL"""
        try:
            domain = urlparse(self.url).netloc.lower()
            return any(supported_domain in domain for supported_domain in self.SUPPORTED_DOMAINS)
        except:
            return False
    
    def scrape(self) -> Optional[ProductData]:
        """Scrape Naseem product page"""
        logger.info(f"Using Naseem scraper for: {self.url}")
        
        try:
            # Step 1: Get structured data from JSON endpoint
            json_data = self._get_json_data(self.url)
            if not json_data:
                logger.error("Failed to get JSON data from Naseem")
                return None
            
            # Step 2: Get detailed description from HTML
            description = self._get_description_from_html(self.url)
            
            # Step 3: Extract image URLs
            image_urls = [img['url'] for img in json_data.get('images', []) if img.get('url')]
            
            # Step 4: Combine and return scraped data
            return ProductData(
                name=json_data.get('name', ''),
                description=description or json_data.get('description', ''),
                image_urls=image_urls,
                handle=json_data.get('handle', ''),
                source=f"Naseem Scraper - {self.url}"
            )
            
        except Exception as e:
            logger.error(f"Error scraping Naseem product: {e}")
            return None
    
    def _get_json_data(self, url: str) -> Optional[Dict[str, Any]]:
        """Get product data from Shopify JSON endpoint"""
        try:
            json_url = url.rstrip('/') + '.json'
            logger.debug(f"Fetching JSON: {json_url}")
            
            response = self.session.get(json_url)
            response.raise_for_status()
            
            data = response.json()
            product = data.get('product', {})
            
            if not product:
                return None
            
            # Extract images
            images = []
            for img in product.get('images', []):
                if img.get('src'):
                    images.append({
                        'url': img['src'],
                        'alt': img.get('alt', ''),
                        'width': img.get('width'),
                        'height': img.get('height')
                    })
            
            return {
                'name': product.get('title', ''),
                'description': product.get('description', ''),
                'handle': product.get('handle', ''),
                'images': images
            }
            
        except Exception as e:
            logger.error(f"Error getting JSON data: {e}")
            return None
    
    def _get_description_from_html(self, url: str) -> str:
        """Extract detailed fragrance description from HTML"""
        try:
            logger.debug(f"Getting description from HTML: {url}")
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            description_parts = []
            
            # Look for accordion-tab elements with product details
            accordion_tabs = soup.find_all('accordion-tab')
            
            for tab in accordion_tabs:
                details = tab.find('details')
                if details:
                    text = details.get_text(strip=True)
                    
                    # Filter out navigation/menu content
                    if (text and len(text) > 50 and 
                        not text.startswith(('Aqua Parfum', 'Collection', 'Home')) and
                        not 'My Account' in text):
                        
                        # Clean up whitespace
                        cleaned = re.sub(r'\s+', ' ', text).strip()
                        
                        # Only add if it contains fragrance-related content
                        if any(keyword in cleaned.lower() for keyword in 
                               ['fragrance', 'notes', 'scent', 'parfum', 'masculine', 'feminine', 'top', 'middle', 'base']):
                            description_parts.append(cleaned)
            
            # Fallback: look for any details element with fragrance content
            if not description_parts:
                all_details = soup.find_all('details')
                for details in all_details:
                    text = details.get_text(strip=True)
                    if (text and len(text) > 50 and 
                        any(keyword in text.lower() for keyword in 
                            ['fragrance', 'notes', 'scent', 'top', 'middle', 'base', 'masculine', 'feminine'])):
                        cleaned = re.sub(r'\s+', ' ', text).strip()
                        description_parts.append(cleaned)
            
            # Join description parts
            full_description = '\n\n'.join(description_parts)
            
            if full_description:
                logger.info(f"Found Naseem description: {len(full_description)} chars")
                return full_description
            else:
                logger.warning("No fragrance description found in HTML")
                return ""
                
        except Exception as e:
            logger.error(f"Error getting description from HTML: {e}")
            return ""