from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class ProductData:
    """Scraped product data"""
    name: str
    description: str
    image_urls: List[str]
    handle: Optional[str] = None  # Shopify handle extracted from competitor site
    raw_data: Optional[Dict[str, Any]] = None
    source: Optional[str] = None

class BaseScraper(ABC):
    """Base class for product scrapers"""
    
    def __init__(self, url: str):
        self.url = url
        self.logger = logger
    
    @abstractmethod
    def can_handle(self) -> bool:
        """Check if this scraper can handle the URL"""
        pass
    
    @abstractmethod
    def scrape(self) -> Optional[ProductData]:
        """Scrape product data from the URL"""
        pass
    
    def clean_description(self, description: str) -> str:
        """Clean and normalize description text"""
        if not description:
            return ""
        
        # Remove excessive whitespace
        lines = description.split('\n')
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned_lines)