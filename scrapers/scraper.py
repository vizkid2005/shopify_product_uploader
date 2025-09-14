from typing import Optional, List
from scrapers.base import ProductData
from scrapers.naseem import NaseemScraper
from scrapers.shopify_json import ShopifyJsonScraper
from scrapers.html_parser import HtmlScraper
from utils.logger import get_logger

logger = get_logger(__name__)

class ProductScraper:
    """Main scraper that tries different strategies in order"""
    
    def __init__(self):
        self.scrapers = [
            NaseemScraper,       # Specialized scraper for Naseem domains
            ShopifyJsonScraper,  # Try JSON first (most reliable)
            HtmlScraper          # Fallback to HTML parsing
        ]
    
    def scrape(self, url: str) -> Optional[ProductData]:
        """Scrape product data using available strategies"""
        logger.info(f"Starting scrape for: {url}")
        
        for scraper_class in self.scrapers:
            scraper = scraper_class(url)
            
            if not scraper.can_handle():
                continue
            
            try:
                result = scraper.scrape()
                if result:
                    logger.info(f"Successfully scraped using {scraper_class.__name__}")
                    return result
            except Exception as e:
                logger.warning(f"{scraper_class.__name__} failed: {e}")
                continue
        
        logger.error(f"All scraping strategies failed for: {url}")
        return None