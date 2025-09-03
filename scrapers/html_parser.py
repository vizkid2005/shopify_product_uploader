import requests
from bs4 import BeautifulSoup
from typing import Optional, List
from scrapers.base import BaseScraper, ProductData
from config.settings import settings
from tenacity import retry, stop_after_attempt, wait_exponential

class HtmlScraper(BaseScraper):
    """Fallback HTML scraper for Shopify stores"""
    
    def can_handle(self) -> bool:
        """This is the fallback scraper, always returns True"""
        return True
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def scrape(self) -> Optional[ProductData]:
        """Scrape product data from HTML"""
        self.logger.info(f"Falling back to HTML scraper: {self.url}")
        
        try:
            headers = {
                'User-Agent': settings.USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml'
            }
            
            response = requests.get(
                self.url,
                headers=headers,
                timeout=settings.SCRAPE_TIMEOUT
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Try multiple strategies to find product name
            name = self._extract_name(soup)
            if not name:
                self.logger.error("Could not extract product name")
                return None
            
            # Extract description
            description = self._extract_description(soup)
            
            # Extract images
            image_urls = self._extract_images(soup)
            
            self.logger.info(f"HTML scrape successful: {name} ({len(image_urls)} images)")
            
            return ProductData(
                name=name,
                description=self.clean_description(description),
                image_urls=image_urls,
                source='html_fallback'
            )
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch HTML: {e}")
            return None
        except Exception as e:
            self.logger.error(f"HTML parsing error: {e}")
            return None
    
    def _extract_name(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product name from HTML"""
        # Try Open Graph title first
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            return og_title['content']
        
        # Try common Shopify selectors
        selectors = [
            'h1.product__title',
            'h1.product-title',
            'h1[itemprop="name"]',
            '.product-single__title',
            'h1'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                return element.get_text(strip=True)
        
        # Try page title as last resort
        if soup.title:
            title = soup.title.get_text(strip=True)
            # Remove common suffixes
            for suffix in [' – ', ' - ', ' | ']:
                if suffix in title:
                    title = title.split(suffix)[0]
            return title
        
        return None
    
    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract product description from HTML"""
        # Try Open Graph description
        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            return og_desc['content']
        
        # Try common description selectors
        selectors = [
            '.product__description',
            '.product-description',
            '[itemprop="description"]',
            '.product-single__description',
            '.rte' # Rich text editor content
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(separator='\n', strip=True)
        
        # Try meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            return meta_desc['content']
        
        return ""
    
    def _extract_images(self, soup: BeautifulSoup) -> List[str]:
        """Extract product images from HTML"""
        image_urls = []
        
        # Try Open Graph image
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_urls.append(og_image['content'])
        
        # Common Shopify image selectors
        selectors = [
            '.product__media img',
            '.product-images img',
            '.product-photo-container img',
            '[data-product-images] img',
            '.product-single__photos img'
        ]
        
        for selector in selectors:
            images = soup.select(selector)
            for img in images:
                src = img.get('src') or img.get('data-src')
                if src:
                    # Clean up Shopify image URLs
                    if src.startswith('//'):
                        src = 'https:' + src
                    # Remove size parameters for full resolution
                    if '?' in src:
                        src = src.split('?')[0]
                    if src not in image_urls:
                        image_urls.append(src)
        
        return image_urls