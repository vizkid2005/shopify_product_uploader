#!/usr/bin/env python3
"""
Shopify Product Uploader - Main CLI Application
ERPNext → Scraping → Processing → Shopify Pipeline
"""

import sys
import argparse
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from config.settings import settings
from utils.logger import setup_logger, get_logger
from clients.erpnext import ERPNextClient
from clients.shopify import ShopifyClient
from scrapers.scraper import ProductScraper
from services.image_manager import ImageManager
from services.seo_optimizer import SEOOptimizer
from services.rate_limiter import RateLimiter
from ui.preview import ProductPreview

logger = get_logger(__name__)

class ProductPipeline:
    """Main orchestrator for the product pipeline"""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        
        # Initialize components
        self.ui = ProductPreview()
        self.rate_limiter = RateLimiter()
        
        try:
            self.erpnext = ERPNextClient()
            self.shopify = ShopifyClient()
            self.scraper = ProductScraper()
            self.image_manager = ImageManager()
            self.seo_optimizer = SEOOptimizer()
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            self.ui.show_error(f"Initialization failed: {e}")
            sys.exit(1)
    
    def test_connections(self) -> bool:
        """Test all API connections"""
        self.ui.show_info("Testing connections...")
        
        if not self.erpnext.test_connection():
            self.ui.show_error("ERPNext connection failed")
            return False
        
        if not self.shopify.test_connection():
            self.ui.show_error("Shopify connection failed")
            return False
        
        if not self.seo_optimizer.test_connection():
            self.ui.show_warning("OpenAI API connection failed - will use fallback descriptions")
        
        self.ui.show_success("All connections successful")
        return True
    
    def scrape_items(self, item_code: Optional[str] = None, limit: Optional[int] = None) -> int:
        """Scrape competitor data and store in ERPNext"""
        self.ui.show_info("Starting scraping process...")
        
        if not self.test_connections():
            return 0
        
        success_count = 0
        error_count = 0
        
        try:
            # Get items to scrape
            if item_code:
                item = self.erpnext.get_item_by_code(item_code)
                if not item:
                    self.ui.show_error(f"Item {item_code} not found")
                    return 0
                items = [item]
            else:
                items = self.erpnext.get_all_items()
                if limit:
                    items = list(items)[:limit]
            
            for i, item in enumerate(items, 1):
                self.ui.show_info(f"[{i}] Scraping: {item.item_code}")
                
                try:
                    # Get competitor URL
                    competitor_url = item.get_priority_link()
                    if not competitor_url:
                        self.ui.show_warning(f"No competitor link for {item.item_code}")
                        continue
                    
                    # Rate limit
                    self.rate_limiter.wait()
                    
                    # Scrape product data
                    scraped_data = self.scraper.scrape(competitor_url)
                    if not scraped_data:
                        self.ui.show_error(f"Failed to scrape {competitor_url}")
                        error_count += 1
                        continue
                    
                    # Prepare scraped data for ERPNext
                    scraped_data_dict = {
                        'images': [
                            {
                                'url': url,
                                'filename': Path(url).name,
                                'is_primary': i == 0,
                                'source': competitor_url,
                                'added_manually': False,
                                'order': i + 1
                            }
                            for i, url in enumerate(scraped_data.image_urls)
                        ],
                        'description': scraped_data.description,
                        'name': scraped_data.name,
                        'handle': scraped_data.handle,  # Include scraped Shopify handle
                        'source_url': competitor_url,
                        'scrape_date': datetime.now().isoformat()
                    }
                    
                    # Update ERPNext with scraped data
                    if self.erpnext.update_scraped_data(item.item_code, scraped_data_dict, dry_run=self.dry_run):
                        success_count += 1
                        self.ui.show_success(f"Scraped {item.item_code}")
                    else:
                        error_count += 1
                        self.ui.show_error(f"Failed to update ERPNext for {item.item_code}")
                
                except Exception as e:
                    logger.error(f"Error scraping {item.item_code}: {e}", exc_info=True)
                    self.ui.show_error(f"Error scraping {item.item_code}: {e}")
                    error_count += 1
        
        except KeyboardInterrupt:
            self.ui.show_warning("Scraping interrupted by user")
        except Exception as e:
            logger.error(f"Fatal error during scraping: {e}", exc_info=True)
            self.ui.show_error(f"Fatal error: {e}")
        
        self.ui.show_info(f"Scraping complete: {success_count} success, {error_count} errors")
        return success_count
    
    def process_items(self, item_code: Optional[str] = None, content_status: str = "Draft", limit: Optional[int] = None) -> int:
        """Process scraped data with AI optimization"""
        self.ui.show_info("Starting processing...")
        
        success_count = 0
        error_count = 0
        
        try:
            # Get items to process
            if item_code:
                item = self.erpnext.get_item_by_code(item_code)
                if not item:
                    self.ui.show_error(f"Item {item_code} not found")
                    return 0
                items = [item]
            else:
                items = self.erpnext.get_items_by_status(content_status=content_status, limit=limit)
            
            for i, item in enumerate(items, 1):
                self.ui.show_info(f"[{i}] Processing: {item.item_code}")
                
                try:
                    # Get SEO title parts
                    title_parts = item.get_seo_title_parts()
                    
                    # Optimize content with AI
                    seo_content = self.seo_optimizer.optimize_content(
                        item.scraped_name or item.shopify_product_name,
                        item.scraped_description or '',
                        item.item_code,
                        title_parts=title_parts
                    )
                    
                    # Add scraped data to processed data for field population
                    processed_data = seo_content.copy()
                    
                    # Populate handle field if empty
                    if not item.shopify_product_handle and item.scraped_handle:
                        processed_data['product_handle'] = item.scraped_handle
                    
                    # Populate name field if empty
                    if not item.shopify_product_name and item.scraped_name:
                        processed_data['product_name'] = item.scraped_name
                    
                    # Update ERPNext with processed data
                    if self.erpnext.update_processed_data(item.item_code, processed_data, dry_run=self.dry_run):
                        success_count += 1
                        self.ui.show_success(f"Processed {item.item_code}")
                    else:
                        error_count += 1
                        self.ui.show_error(f"Failed to update processed data for {item.item_code}")
                
                except Exception as e:
                    logger.error(f"Error processing {item.item_code}: {e}", exc_info=True)
                    self.ui.show_error(f"Error processing {item.item_code}: {e}")
                    error_count += 1
        
        except KeyboardInterrupt:
            self.ui.show_warning("Processing interrupted by user")
        except Exception as e:
            logger.error(f"Fatal error during processing: {e}", exc_info=True)
            self.ui.show_error(f"Fatal error: {e}")
        
        self.ui.show_info(f"Processing complete: {success_count} success, {error_count} errors")
        return success_count
    
    def upload_items(self, item_code: Optional[str] = None, content_status: str = "Processed", limit: Optional[int] = None) -> int:
        """Upload processed items to Shopify"""
        self.ui.show_info("Starting Shopify upload...")
        
        if not self.test_connections():
            return 0
        
        success_count = 0
        error_count = 0
        
        try:
            # Get items to upload
            if item_code:
                item = self.erpnext.get_item_by_code(item_code)
                if not item:
                    self.ui.show_error(f"Item {item_code} not found")
                    return 0
                items = [item]
            else:
                items = self.erpnext.get_items_by_status(content_status=content_status, limit=limit)
            
            for i, item in enumerate(items, 1):
                self.ui.show_info(f"[{i}] Uploading: {item.item_code}")
                
                try:
                    # Check if already exists in Shopify
                    existing_product = self.shopify.get_existing_product(item.shopify_product_handle, item.item_code)
                    logger.info(existing_product)
                    is_update = existing_product is not None
                    
                    # Download images from JSON
                    image_files = []
                    if item.scraped_images:
                        self.ui.show_info(f"Downloading {len(item.scraped_images)} images...")
                        for img_data in item.scraped_images:
                            try:
                                # Download image from URL
                                image_path = self.image_manager.download_image_for_item(
                                    img_data['url'], 
                                    item.item_code,
                                    img_data.get('filename', Path(img_data['url']).name)
                                )
                                if image_path:
                                    image_files.append(image_path)
                            except Exception as e:
                                logger.warning(f"Failed to download image {img_data['url']}: {e}")
                    
                    if not image_files:
                        self.ui.show_warning(f"No images downloaded for {item.item_code}")
                        self.erpnext.update_sync_status(item.item_code, "Error", dry_run=self.dry_run)
                        error_count += 1
                        continue
                    
                    # Show preview and get approval
                    if not self.dry_run:
                        action_text = "UPDATE" if is_update else "CREATE"
                        self.ui.show_info(f"Action: {action_text} product in Shopify")
                        
                        self.ui.display_preview(
                            item.item_code,
                            item.shopify_product_name,
                            item.shopify_description_html or "No description",
                            image_files,
                            item.scrape_source_url or "",
                            seo_title=item.shopify_seo_title,
                            meta_description=item.shopify_meta_description
                        )
                        
                        approved, price = self.ui.get_approval_and_price()
                        if not approved:
                            self.ui.show_info(f"Upload rejected for {item.item_code}")
                            continue
                    else:
                        price = "99.99"  # Default price for dry run
                    
                    # Create or update product in Shopify
                    if is_update:
                        # Extract product ID from existing product
                        product_id = existing_product['id']
                        
                        product = self.shopify.update_product(
                            product_id=product_id,
                            item_code=item.item_code,
                            title=item.shopify_product_name,
                            description_html=item.shopify_description_html or "",
                            image_paths=image_files,
                            price=price,
                            handle=item.shopify_product_handle,
                            seo_title=item.shopify_seo_title,
                            meta_description=item.shopify_meta_description
                        )
                        action_text = "updated"
                    else:
                        product = self.shopify.create_product(
                            item_code=item.item_code,
                            title=item.shopify_product_name,
                            description_html=item.shopify_description_html or "",
                            image_paths=image_files,
                            price=price,
                            handle=item.shopify_product_handle,
                            seo_title=item.shopify_seo_title,
                            meta_description=item.shopify_meta_description
                        )
                        action_text = "created"
                    
                    if product:
                        self.erpnext.update_sync_status(
                            item.item_code, 
                            "Synced", 
                            product.get('id'),
                            dry_run=self.dry_run
                        )
                        success_count += 1
                        self.ui.show_success(f"Successfully {action_text} {item.item_code} in Shopify")
                    else:
                        self.erpnext.update_sync_status(item.item_code, "Error", dry_run=self.dry_run)
                        error_count += 1
                        self.ui.show_error(f"Failed to {action_text.split()[0]} {item.item_code}")
                
                except Exception as e:
                    logger.error(f"Error uploading {item.item_code}: {e}", exc_info=True)
                    self.ui.show_error(f"Error uploading {item.item_code}: {e}")
                    self.erpnext.update_sync_status(item.item_code, "Error", dry_run=self.dry_run)
                    error_count += 1
        
        except KeyboardInterrupt:
            self.ui.show_warning("Upload interrupted by user")
        except Exception as e:
            logger.error(f"Fatal error during upload: {e}", exc_info=True)
            self.ui.show_error(f"Fatal error: {e}")
        
        self.ui.show_info(f"Upload complete: {success_count} success, {error_count} errors")
        return success_count
    
    def run_pipeline(self, item_code: Optional[str] = None, limit: Optional[int] = None) -> bool:
        """Run full pipeline: scrape → process → upload"""
        self.ui.show_info("Starting full pipeline...")
        
        # Step 1: Scrape
        scraped = self.scrape_items(item_code, limit)
        if scraped == 0:
            self.ui.show_error("No items scraped, stopping pipeline")
            return False
        
        # Step 2: Process
        processed = self.process_items(item_code, "Draft", limit)
        if processed == 0:
            self.ui.show_error("No items processed, stopping pipeline")
            return False
        
        # Step 3: Upload
        uploaded = self.upload_items(item_code, "Processed", limit)
        
        self.ui.show_success(f"Pipeline complete: {scraped} scraped, {processed} processed, {uploaded} uploaded")
        return uploaded > 0
    
    def show_status(self, item_code: Optional[str] = None, detailed: bool = False) -> None:
        """Show current pipeline status"""
        self.ui.show_info("Pipeline Status")
        
        if item_code:
            # Show single item status
            item = self.erpnext.get_item_by_code(item_code)
            if not item:
                self.ui.show_error(f"Item {item_code} not found")
                return
            
            self.ui.show_info(f"Item: {item.item_code}")
            self.ui.show_info(f"  Content Status: {item.content_status or 'None'}")
            self.ui.show_info(f"  Sync Status: {item.shopify_sync_status or 'None'}")
            self.ui.show_info(f"  Last Sync: {item.last_shopify_sync or 'Never'}")
            if item.scraped_images:
                self.ui.show_info(f"  Images: {len(item.scraped_images)}")
            if item.shopify_product_id:
                self.ui.show_info(f"  Shopify ID: {item.shopify_product_id}")
        else:
            # Show overall statistics
            stats = {}
            
            # Get counts by content status
            for status in ["Draft", "Processed", "Approved"]:
                count = len(list(self.erpnext.get_items_by_status(content_status=status, limit=1000)))
                stats[f"Content {status}"] = count
            
            # Get counts by sync status  
            for status in ["Pending", "Synced", "Error", "Skipped"]:
                count = len(list(self.erpnext.get_items_by_status(sync_status=status, limit=1000)))
                stats[f"Sync {status}"] = count
            
            self.ui.show_info("Overall Statistics:")
            for status, count in stats.items():
                self.ui.show_info(f"  {status}: {count}")

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="ERPNext → Shopify Product Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  scrape    Scrape competitor data into ERPNext
  process   Process scraped data with AI optimization  
  upload    Upload processed products to Shopify
  pipeline  Run full scrape → process → upload pipeline
  status    Show pipeline status and statistics

Examples:
  %(prog)s scrape --limit 10 --dry-run
  %(prog)s process --status Draft --limit 5
  %(prog)s upload --status Processed
  %(prog)s pipeline --item-code ITEM-001
  %(prog)s status --item-code ITEM-001 --detailed
        """
    )
    
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')
    parser.add_argument('--item-code', 
                        help='Process a single item by code')
    parser.add_argument('--limit', type=int,
                        help='Maximum number of items to process')
    
    # Create subparsers
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Scrape command
    scrape_parser = subparsers.add_parser('scrape', help='Scrape competitor data into ERPNext')
    scrape_parser.add_argument('--item-code', help='Scrape a single item')
    scrape_parser.add_argument('--limit', type=int, help='Maximum items to scrape')
    scrape_parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    
    # Process command
    process_parser = subparsers.add_parser('process', help='Process scraped data with AI')
    process_parser.add_argument('--item-code', help='Process a single item')
    process_parser.add_argument('--status', default='Draft', help='Content status to process (default: Draft)')
    process_parser.add_argument('--limit', type=int, help='Maximum items to process')
    process_parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    
    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload processed products to Shopify')
    upload_parser.add_argument('--item-code', help='Upload a single item')
    upload_parser.add_argument('--status', default='Processed', help='Content status to upload (default: Processed)')
    upload_parser.add_argument('--limit', type=int, help='Maximum items to upload')
    upload_parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    
    # Pipeline command
    pipeline_parser = subparsers.add_parser('pipeline', help='Run full scrape → process → upload pipeline')
    pipeline_parser.add_argument('--item-code', help='Run pipeline for single item')
    pipeline_parser.add_argument('--limit', type=int, help='Maximum items to process')
    pipeline_parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show pipeline status')
    status_parser.add_argument('--item-code', help='Show status for single item')
    status_parser.add_argument('--detailed', action='store_true', help='Show detailed information')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Validate settings
    try:
        settings.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    
    # Initialize pipeline
    pipeline = ProductPipeline(dry_run=args.dry_run)
    
    # Execute command
    try:
        if args.command == 'scrape':
            pipeline.scrape_items(args.item_code, args.limit)
        elif args.command == 'process':
            pipeline.process_items(args.item_code, args.status, args.limit)
        elif args.command == 'upload':
            pipeline.upload_items(args.item_code, args.status, args.limit)
        elif args.command == 'pipeline':
            pipeline.run_pipeline(args.item_code, args.limit)
        elif args.command == 'status':
            pipeline.show_status(args.item_code, args.detailed)
        else:
            parser.print_help()
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()