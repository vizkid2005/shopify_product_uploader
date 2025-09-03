from typing import List, Dict, Any, Optional, Generator
from dataclasses import dataclass
import requests
from frappeclient import FrappeClient
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

@dataclass
class ERPNextItem:
    """Represents an ERPNext Item with competitor links"""
    item_code: str
    item_name: str
    description: Optional[str] = None
    competitor_link_1: Optional[str] = None
    competitor_link_2: Optional[str] = None
    competitor_link_3: Optional[str] = None
    
    def get_priority_link(self) -> Optional[str]:
        """Get the highest priority competitor link based on domain"""
        links = [
            self.competitor_link_1,
            self.competitor_link_2,
            self.competitor_link_3
        ]
        
        for domain in settings.COMPETITOR_PRIORITY:
            for link in links:
                if link and domain in link:
                    logger.debug(f"Selected link for {self.item_code}: {link}")
                    return link
        
        # Return first non-empty link if no priority matches
        for link in links:
            if link:
                logger.debug(f"Using fallback link for {self.item_code}: {link}")
                return link
        
        return None

class ERPNextClient:
    """Client for interacting with ERPNext API"""
    
    def __init__(self, base_url: Optional[str] = None, 
                 api_key: Optional[str] = None,
                 api_secret: Optional[str] = None):
        self.base_url = base_url or settings.ERP_BASE_URL
        self.api_key = api_key or settings.ERP_API_KEY
        self.api_secret = api_secret or settings.ERP_API_SECRET
        
        if not all([self.base_url, self.api_key, self.api_secret]):
            raise ValueError("ERPNext credentials not configured")
        
        # Initialize Frappe client
        self.client = FrappeClient(self.base_url, verify=False)
        self.client.authenticate(self.api_key, self.api_secret)
        self.client.session.verify = False
        
        logger.info(f"Connected to ERPNext at {self.base_url}")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def get_items_page(self, start: int = 0, page_size: int = 10) -> List[Dict[str, Any]]:
        """Fetch a page of items from ERPNext"""
        logger.debug(f"Fetching items page: start={start}, size={page_size}")
        
        try:
            items = self.client.get_list(
                'Item',
                fields=[
                    'item_code', 
                    'item_name', 
                    'description',
                    'custom_competitor_link_1',
                    'custom_competitor_link_2', 
                    'custom_competitor_link_3'
                ],
                filters={
                    'disabled': 0,
                    # 'is_sales_item': 1
                },
                limit_start=start,
                limit_page_length=page_size,
                order_by='item_code'
            )
            
            logger.info(f"Fetched {len(items)} items from ERPNext")
            print(str(items))
            doc = self.client.get_doc('Customer', 'Egycan Foods')
            print(doc)
            logger.info("huzee")
            return items
            
        except Exception as e:
            logger.error(f"Error fetching items from ERPNext: {e}")
            raise
    
    def get_all_items(self, page_size: Optional[int] = None) -> Generator[ERPNextItem, None, None]:
        """Generator that yields all items from ERPNext"""
        page_size = page_size or settings.PAGE_SIZE
        start = 0
        total_fetched = 0
        
        while True:
            items_data = self.get_items_page(start, page_size)
            
            if not items_data:
                logger.info(f"Finished fetching all items. Total: {total_fetched}")
                break
            
            for item_data in items_data:
                item = ERPNextItem(
                    item_code=item_data.get('item_code', ''),
                    item_name=item_data.get('item_name', ''),
                    description=item_data.get('description'),
                    competitor_link_1=item_data.get('custom_competitor_link_1'),
                    competitor_link_2=item_data.get('custom_competitor_link_2'),
                    competitor_link_3=item_data.get('custom_competitor_link_3')
                )
                
                # Only yield items that have at least one competitor link
                if item.get_priority_link():
                    total_fetched += 1
                    yield item
                else:
                    logger.warning(f"Skipping item {item.item_code}: no competitor links")
            
            start += page_size
    
    def get_item_by_code(self, item_code: str) -> Optional[ERPNextItem]:
        """Fetch a single item by code"""
        try:
            item_data = self.client.get_doc('Item', item_code)
            

            return ERPNextItem(
                item_code=item_data.get('item_code', ''),
                item_name=item_data.get('item_name', ''),
                description=item_data.get('description'),
                competitor_link_1=item_data.get('custom_competitor_link_1'),
                competitor_link_2=item_data.get('custom_competitor_link_2'),
                competitor_link_3=item_data.get('custom_competitor_link_3')
            )
        except Exception as e:
            logger.error(f"Error fetching item {item_code}: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test the connection to ERPNext"""
        try:
            # Try to fetch one item to test connection
            self.get_items_page(0, 1)
            logger.info("ERPNext connection test successful")
            return True
        except Exception as e:
            logger.error(f"ERPNext connection test failed: {e}")
            return False