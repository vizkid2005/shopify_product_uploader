from typing import List, Dict, Any, Optional, Generator
from dataclasses import dataclass
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import get_logger
from config.settings import settings
import json

logger = get_logger(__name__)

@dataclass
class ERPNextItem:
    """Represents an ERPNext Item with competitor links and scraped data"""
    # Core item data
    item_code: str
    item_name: str
    description: Optional[str] = None
    
    # Shopify mapping fields
    shopify_product_name: Optional[str] = None
    shopify_product_handle: Optional[str] = None
    brand_custom: Optional[str] = None
    gender: Optional[str] = None
    quantity: Optional[str] = None
    product_type: Optional[str] = None
    
    # Competitor links
    competitor_link_1: Optional[str] = None
    competitor_link_2: Optional[str] = None
    competitor_link_3: Optional[str] = None
    
    # Scraped data fields
    scraped_images: Optional[List[Dict[str, Any]]] = None
    scraped_description: Optional[str] = None
    scraped_name: Optional[str] = None
    scraped_handle: Optional[str] = None
    scrape_source_url: Optional[str] = None
    scrape_date: Optional[str] = None
    
    # Processed content fields
    shopify_description_html: Optional[str] = None
    shopify_seo_title: Optional[str] = None
    shopify_meta_description: Optional[str] = None
    
    # Status fields
    content_status: Optional[str] = None
    shopify_sync_status: Optional[str] = None
    last_shopify_sync: Optional[str] = None
    shopify_product_id: Optional[str] = None
    
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
    
    def get_seo_title_parts(self) -> List[str]:
        """Get parts for SEO title construction using | separator"""
        parts = []
        
        # Always start with the product name
        if self.shopify_product_name:
            parts.append(self.shopify_product_name.strip())
        
        # Add product type if available (e.g., "Eau de Parfum", "Attar")
        if self.product_type:
            parts.append(self.product_type.strip())
        
        # Add brand if available
        if self.brand_custom:
            parts.append(self.brand_custom.strip())
        
        # Add gender if available
        if self.gender:
            parts.append(self.gender.strip())
        
        # Add quantity if available
        if self.quantity:
            parts.append(f"{self.quantity.strip()}ml")
        
        return parts

class ERPNextClient:
    """Client for interacting with ERPNext API using REST"""
    
    def __init__(self, base_url: Optional[str] = None, 
                 api_key: Optional[str] = None,
                 api_secret: Optional[str] = None):
        self.base_url = base_url or settings.ERP_BASE_URL
        self.api_key = api_key or settings.ERP_API_KEY
        self.api_secret = api_secret or settings.ERP_API_SECRET
        
        if not all([self.base_url, self.api_key, self.api_secret]):
            raise ValueError("ERPNext credentials not configured")
        
        # Ensure base URL ends with /api/resource
        if not self.base_url.endswith('/'):
            self.base_url += '/'
        if not self.base_url.endswith('api/resource/'):
            self.base_url += 'api/resource/'
        
        # Set up session with authentication headers
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {self.api_key}:{self.api_secret}',
            'Content-Type': 'application/json'
        })
        self.session.verify = False
        
        logger.info(f"Connected to ERPNext at {self.base_url}")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def get_items_page(self, start: int = 0, page_size: int = 10) -> List[Dict[str, Any]]:
        """Fetch a page of items from ERPNext"""
        logger.debug(f"Fetching items page: start={start}, size={page_size}")
        
        try:
            # Construct the URL for Item list
            url = f"{self.base_url}Item"
            
            params = {
                'fields': json.dumps([
                    # Core fields
                    'item_code', 
                    'item_name', 
                    'description',
                    
                    # Shopify mapping fields
                    'custom_shopify_product_name',
                    'custom_shopify_product_handle',
                    'custom_brand_custom',
                    'custom_gender',
                    'custom_quantity',
                    'custom_product_type',
                    
                    # Competitor links
                    'custom_competitor_link_1',
                    'custom_competitor_link_2', 
                    'custom_competitor_link_3',
                    
                    # Scraped data fields
                    'custom_scraped_images',
                    'custom_scraped_description',
                    'custom_scraped_name',
                    'custom_scraped_handle',
                    'custom_scrape_source_url',
                    'custom_scrape_date',
                    
                    # Processed content fields
                    'custom_shopify_description_html',
                    'custom_shopify_seo_title',
                    'custom_shopify_meta_description',
                    
                    # Status fields
                    'custom_content_status',
                    'custom_shopify_sync_status',
                    'custom_last_shopify_sync',
                    'custom_shopify_product_id'
                ]),
                'filters': json.dumps({
                    'disabled': 0
                }),
                'limit_start': start,
                'limit_page_length': page_size,
                'order_by': 'item_code'
            }
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            items = data.get('data', [])
            
            logger.info(f"Fetched {len(items)} items from ERPNext")
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
                # Parse scraped images JSON if present
                scraped_images = None
                if item_data.get('custom_scraped_images'):
                    try:
                        scraped_images = json.loads(item_data['custom_scraped_images'])
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"Invalid JSON in scraped_images for {item_data.get('item_code')}")
                        scraped_images = []

                item = ERPNextItem(
                    # Core fields
                    item_code=item_data.get('item_code', ''),
                    item_name=item_data.get('item_name', ''),
                    description=item_data.get('description'),
                    
                    # Shopify mapping fields
                    shopify_product_name=item_data.get('custom_shopify_product_name'),
                    shopify_product_handle=item_data.get('custom_shopify_product_handle'),
                    brand_custom=item_data.get('custom_brand_custom'),
                    gender=item_data.get('custom_gender'),
                    quantity=item_data.get('custom_quantity'),
                    
                    # Competitor links
                    competitor_link_1=item_data.get('custom_competitor_link_1'),
                    competitor_link_2=item_data.get('custom_competitor_link_2'),
                    competitor_link_3=item_data.get('custom_competitor_link_3'),
                    
                    # Scraped data fields
                    scraped_images=scraped_images,
                    scraped_description=item_data.get('custom_scraped_description'),
                    scraped_name=item_data.get('custom_scraped_name'),
                    scraped_handle=item_data.get('custom_scraped_handle'),
                    scrape_source_url=item_data.get('custom_scrape_source_url'),
                    scrape_date=item_data.get('custom_scrape_date'),
                    
                    # Processed content fields
                    shopify_description_html=item_data.get('custom_shopify_description_html'),
                    shopify_seo_title=item_data.get('custom_shopify_seo_title'),
                    shopify_meta_description=item_data.get('custom_shopify_meta_description'),
                    
                    # Status fields
                    content_status=item_data.get('custom_content_status'),
                    shopify_sync_status=item_data.get('custom_shopify_sync_status'),
                    last_shopify_sync=item_data.get('custom_last_shopify_sync'),
                    shopify_product_id=item_data.get('custom_shopify_product_id')
                )
                
                # Only yield items that have competitor links (shopify fields are optional for scraping)
                if item.get_priority_link():
                    total_fetched += 1
                    yield item
                else:
                    logger.warning(f"Skipping item {item.item_code}: no competitor links")
            
            start += page_size
    
    def get_item_by_code(self, item_code: str) -> Optional[ERPNextItem]:
        """Fetch a single item by code"""
        try:
            url = f"{self.base_url}Item/{item_code}"
            
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            item_data = data.get('data', {})
            
            # Parse scraped images JSON if present
            scraped_images = None
            if item_data.get('custom_scraped_images'):
                try:
                    scraped_images = json.loads(item_data['custom_scraped_images'])
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Invalid JSON in scraped_images for {item_code}")
                    scraped_images = []

            return ERPNextItem(
                # Core fields
                item_code=item_data.get('item_code', ''),
                item_name=item_data.get('item_name', ''),
                description=item_data.get('description'),
                
                # Shopify mapping fields
                shopify_product_name=item_data.get('custom_shopify_product_name'),
                shopify_product_handle=item_data.get('custom_shopify_product_handle'),
                brand_custom=item_data.get('custom_brand_custom'),
                gender=item_data.get('custom_gender'),
                quantity=item_data.get('custom_quantity'),
                product_type=item_data.get('custom_product_type'),
                
                # Competitor links
                competitor_link_1=item_data.get('custom_competitor_link_1'),
                competitor_link_2=item_data.get('custom_competitor_link_2'),
                competitor_link_3=item_data.get('custom_competitor_link_3'),
                
                # Scraped data fields
                scraped_images=scraped_images,
                scraped_description=item_data.get('custom_scraped_description'),
                scraped_name=item_data.get('custom_scraped_name'),
                scraped_handle=item_data.get('custom_scraped_handle'),
                scrape_source_url=item_data.get('custom_scrape_source_url'),
                scrape_date=item_data.get('custom_scrape_date'),
                
                # Processed content fields
                shopify_description_html=item_data.get('custom_shopify_description_html'),
                shopify_seo_title=item_data.get('custom_shopify_seo_title'),
                shopify_meta_description=item_data.get('custom_shopify_meta_description'),
                
                # Status fields
                content_status=item_data.get('custom_content_status'),
                shopify_sync_status=item_data.get('custom_shopify_sync_status'),
                last_shopify_sync=item_data.get('custom_last_shopify_sync'),
                shopify_product_id=item_data.get('custom_shopify_product_id')
            )
        except Exception as e:
            logger.error(f"Error fetching item {item_code}: {e}")
            return None
    
    def update_scraped_data(self, item_code: str, scraped_data: Dict[str, Any], dry_run: bool = False) -> bool:
        """Update scraped data fields in ERPNext"""
        if dry_run:
            logger.info(f"DRY RUN: Would update scraped data for {item_code}")
            logger.info(f"Scraped images: {len(scraped_data.get('images', []))} images")
            logger.info(f"Scraped description: {scraped_data.get('description', '')[:100]}...")
            logger.info(f"Scraped name: {scraped_data.get('name', '')}")
            logger.info(f"Scraped handle: {scraped_data.get('handle', '')}")
            logger.info(f"Source URL: {scraped_data.get('source_url', '')}")
            return True

        try:
            url = f"{self.base_url}Item/{item_code}"
            
            # Prepare update data
            update_data = {
                "custom_scraped_images": json.dumps(scraped_data.get('images', [])),
                "custom_scraped_description": scraped_data.get('description', ''),
                "custom_scraped_name": scraped_data.get('name', ''),
                "custom_scraped_handle": scraped_data.get('handle', ''),
                "custom_scrape_source_url": scraped_data.get('source_url', ''),
                "custom_scrape_date": scraped_data.get('scrape_date', ''),
                "custom_content_status": "Draft"
            }
            
            response = self.session.put(url, json=update_data)
            response.raise_for_status()
            
            logger.info(f"Successfully updated scraped data for {item_code}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating scraped data for {item_code}: {e}")
            return False

    def update_processed_data(self, item_code: str, processed_data: Dict[str, Any], dry_run: bool = False) -> bool:
        """Update processed content fields in ERPNext"""
        if dry_run:
            logger.info(f"DRY RUN: Would update processed data for {item_code}")
            logger.info(f"SEO title: {processed_data.get('seo_title', '')}")
            logger.info(f"Meta description: {processed_data.get('meta_description', '')}")
            logger.info(f"Description HTML: {len(processed_data.get('description_html', ''))} chars")
            logger.info(f"Product handle: {processed_data.get('product_handle', '')}")
            logger.info(f"Product name: {processed_data.get('product_name', '')}")
            return True

        try:
            url = f"{self.base_url}Item/{item_code}"
            
            # Prepare update data
            update_data = {
                "custom_shopify_description_html": processed_data.get('description_html', ''),
                "custom_shopify_seo_title": processed_data.get('seo_title', ''),
                "custom_shopify_meta_description": processed_data.get('meta_description', ''),
                "custom_content_status": "Processed"
            }
            
            # Populate handle field if empty and scraped handle exists
            if processed_data.get('product_handle'):
                update_data["custom_shopify_product_handle"] = processed_data['product_handle']
            
            # Populate name field if empty and scraped name exists
            if processed_data.get('product_name'):
                update_data["custom_shopify_product_name"] = processed_data['product_name']
            
            response = self.session.put(url, json=update_data)
            response.raise_for_status()
            
            logger.info(f"Successfully updated processed data for {item_code}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating processed data for {item_code}: {e}")
            return False

    def update_sync_status(self, item_code: str, status: str, shopify_product_id: Optional[str] = None, dry_run: bool = False) -> bool:
        """Update Shopify sync status in ERPNext"""
        if dry_run:
            logger.info(f"DRY RUN: Would update sync status for {item_code} to '{status}'")
            if shopify_product_id:
                logger.info(f"Shopify product ID: {shopify_product_id}")
            return True

        try:
            url = f"{self.base_url}Item/{item_code}"
            
            # Prepare update data
            from datetime import datetime
            update_data = {
                "custom_shopify_sync_status": status,
                "custom_last_shopify_sync": datetime.now().isoformat()
            }
            
            if shopify_product_id:
                update_data["custom_shopify_product_id"] = shopify_product_id
            
            response = self.session.put(url, json=update_data)
            response.raise_for_status()
            
            logger.info(f"Successfully updated sync status for {item_code} to '{status}'")
            return True
            
        except Exception as e:
            logger.error(f"Error updating sync status for {item_code}: {e}")
            return False

    def get_items_by_status(self, content_status: Optional[str] = None, 
                           sync_status: Optional[str] = None,
                           limit: Optional[int] = None) -> Generator[ERPNextItem, None, None]:
        """Get items filtered by status"""
        filters = {
            'disabled': 0
        }
        
        if content_status:
            filters['custom_content_status'] = content_status
        if sync_status:
            filters['custom_shopify_sync_status'] = sync_status

        start = 0
        page_size = 100
        total_fetched = 0
        
        while True:
            if limit and total_fetched >= limit:
                break
                
            current_page_size = min(page_size, limit - total_fetched) if limit else page_size
            
            try:
                url = f"{self.base_url}Item"
                
                params = {
                    'fields': json.dumps([
                        # Core fields
                        'item_code', 'item_name', 'description',
                        
                        # Shopify mapping fields
                        'custom_shopify_product_name', 'custom_shopify_product_handle',
                        'custom_brand_custom', 'custom_gender', 'custom_quantity', 'custom_product_type',
                        
                        # Competitor links
                        'custom_competitor_link_1', 'custom_competitor_link_2', 'custom_competitor_link_3',
                        
                        # Scraped data fields
                        'custom_scraped_images', 'custom_scraped_description', 'custom_scraped_name',
                        'custom_scraped_handle', 'custom_scrape_source_url', 'custom_scrape_date',
                        
                        # Processed content fields
                        'custom_shopify_description_html', 'custom_shopify_seo_title', 'custom_shopify_meta_description',
                        
                        # Status fields
                        'custom_content_status', 'custom_shopify_sync_status', 'custom_last_shopify_sync', 'custom_shopify_product_id'
                    ]),
                    'filters': json.dumps(filters),
                    'limit_start': start,
                    'limit_page_length': current_page_size,
                    'order_by': 'item_code'
                }
                
                response = self.session.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                items_data = data.get('data', [])
                
                if not items_data:
                    logger.info(f"Finished fetching items by status. Total: {total_fetched}")
                    break
                
                for item_data in items_data:
                    # Parse scraped images JSON if present
                    scraped_images = None
                    if item_data.get('custom_scraped_images'):
                        try:
                            scraped_images = json.loads(item_data['custom_scraped_images'])
                        except (json.JSONDecodeError, TypeError):
                            logger.warning(f"Invalid JSON in scraped_images for {item_data.get('item_code')}")
                            scraped_images = []

                    item = ERPNextItem(
                        # Core fields
                        item_code=item_data.get('item_code', ''),
                        item_name=item_data.get('item_name', ''),
                        description=item_data.get('description'),
                        
                        # Shopify mapping fields
                        shopify_product_name=item_data.get('custom_shopify_product_name'),
                        shopify_product_handle=item_data.get('custom_shopify_product_handle'),
                        brand_custom=item_data.get('custom_brand_custom'),
                        gender=item_data.get('custom_gender'),
                        quantity=item_data.get('custom_quantity'),
                        product_type=item_data.get('custom_product_type'),
                        
                        # Competitor links
                        competitor_link_1=item_data.get('custom_competitor_link_1'),
                        competitor_link_2=item_data.get('custom_competitor_link_2'),
                        competitor_link_3=item_data.get('custom_competitor_link_3'),
                        
                        # Scraped data fields
                        scraped_images=scraped_images,
                        scraped_description=item_data.get('custom_scraped_description'),
                        scraped_name=item_data.get('custom_scraped_name'),
                        scraped_handle=item_data.get('custom_scraped_handle'),
                        scrape_source_url=item_data.get('custom_scrape_source_url'),
                        scrape_date=item_data.get('custom_scrape_date'),
                        
                        # Processed content fields
                        shopify_description_html=item_data.get('custom_shopify_description_html'),
                        shopify_seo_title=item_data.get('custom_shopify_seo_title'),
                        shopify_meta_description=item_data.get('custom_shopify_meta_description'),
                        
                        # Status fields
                        content_status=item_data.get('custom_content_status'),
                        shopify_sync_status=item_data.get('custom_shopify_sync_status'),
                        last_shopify_sync=item_data.get('custom_last_shopify_sync'),
                        shopify_product_id=item_data.get('custom_shopify_product_id')
                    )

                    total_fetched += 1
                    yield item
                    
                    if limit and total_fetched >= limit:
                        break
                
                start += current_page_size
                
            except Exception as e:
                logger.error(f"Error fetching items by status: {e}")
                break

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