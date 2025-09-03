#!/usr/bin/env python3
"""
Shopify Product Uploader - Main CLI Application
Uploads products from ERPNext to Shopify with SEO optimization
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

from config.settings import settings
from utils.logger import setup_logger, get_logger
from clients.erpnext import ERPNextClient
from clients.shopify import ShopifyClient
from scrapers.scraper import ProductScraper
from services.image_manager import ImageManager
from services.seo_optimizer import SEOOptimizer
from services.state_manager import StateManager, ProcessStatus
from services.rate_limiter import RateLimiter
from ui.preview import ProductPreview

logger = get_logger(__name__)

class ProductUploader:
    """Main orchestrator for product upload process"""
    
    def __init__(self, args):
        self.args = args
        self.dry_run = args.dry_run or settings.DRY_RUN
        
        # Initialize components
        self.ui = ProductPreview()
        self.state_manager = StateManager()
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
            self.ui.show_warning("ChatGPT API connection failed - will use fallback descriptions")
        
        self.ui.show_success("All connections successful")
        return True
    
    def process_item(self, item) -> bool:
        """Process a single ERPNext item"""
        item_code = item.item_code
        
        # Check if already processed
        state = self.state_manager.get_product_state(item_code)
        if state and state['status'] == ProcessStatus.UPLOADED.value:
            logger.info(f"Skipping {item_code}: already uploaded")
            return True
        
        # Check if exists in Shopify
        if self.shopify.product_exists(item_code):
            self.ui.show_info(f"Product {item_code} already exists in Shopify")
            self.state_manager.update_product_state(
                item_code, 
                ProcessStatus.SKIPPED,
                error_message="Already exists in Shopify"
            )
            return True
        
        try:
            # Get competitor URL
            competitor_url = item.get_priority_link()
            if not competitor_url:
                self.ui.show_warning(f"No competitor link for {item_code}")
                self.state_manager.mark_failed(item_code, "No competitor links")
                return False
            
            self.ui.show_info(f"Processing: {item_code} from {competitor_url}")
            
            # Rate limit before scraping
            self.rate_limiter.wait()
            
            # Scrape product data
            scraped_data = self.scraper.scrape(competitor_url)
            if not scraped_data:
                self.ui.show_error(f"Failed to scrape {competitor_url}")
                self.state_manager.mark_failed(item_code, "Scraping failed")
                return False
            
            self.state_manager.update_product_state(
                item_code,
                ProcessStatus.SCRAPED,
                competitor_url=competitor_url,
                product_name=scraped_data.name,
                description=scraped_data.description,
                image_urls=scraped_data.image_urls
            )
            
            # Download images
            self.ui.show_info(f"Downloading {len(scraped_data.image_urls)} images...")
            image_files = self.image_manager.download_product_images(
                item_code, 
                scraped_data.image_urls
            )
            
            if not image_files:
                self.ui.show_error("No images downloaded")
                self.state_manager.mark_failed(item_code, "No images downloaded")
                return False
            
            self.state_manager.update_product_state(
                item_code,
                ProcessStatus.IMAGES_DOWNLOADED,
                image_paths=[str(p) for p in image_files]
            )
            
            # Optimize description with Claude
            self.ui.show_info("Optimizing description with AI...")
            optimized_description = self.seo_optimizer.optimize_description(
                scraped_data.name,
                scraped_data.description,
                item_code
            )
            
            self.state_manager.update_product_state(
                item_code,
                ProcessStatus.OPTIMIZED,
                optimized_description=optimized_description
            )
            
            # Show preview
            self.ui.display_preview(
                item_code,
                scraped_data.name,
                optimized_description,
                image_files,
                competitor_url
            )
            
            # Get approval and price
            if settings.APPROVAL_MODE == "auto":
                approved = True
                price = self.args.default_price or "99.99"
                self.ui.show_info(f"Auto-approval mode: using price ${price}")
            else:
                # Check if user wants to edit description
                if self.ui.ask_edit_description():
                    optimized_description = self.ui.edit_description(optimized_description)
                
                approved, price = self.ui.get_approval_and_price()
            
            if not approved:
                self.state_manager.update_product_state(
                    item_code,
                    ProcessStatus.SKIPPED,
                    error_message="User rejected"
                )
                return True
            
            self.state_manager.update_product_state(
                item_code,
                ProcessStatus.APPROVED,
                price=price
            )
            
            # Upload to Shopify
            if self.dry_run:
                self.ui.show_info("DRY RUN: Would upload to Shopify")
                self.ui.show_success(f"DRY RUN: Product {item_code} processed successfully")
            else:
                self.ui.show_info("Uploading to Shopify...")
                
                product = self.shopify.create_product(
                    item_code=item_code,
                    title=scraped_data.name,
                    description_html=optimized_description,
                    image_paths=image_files,
                    price=price
                )
                
                if product:
                    self.state_manager.update_product_state(
                        item_code,
                        ProcessStatus.UPLOADED,
                        shopify_product_id=product.get('id')
                    )
                    self.ui.show_success(f"Product {item_code} uploaded successfully!")
                else:
                    self.state_manager.mark_failed(item_code, "Upload to Shopify failed")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing {item_code}: {e}", exc_info=True)
            self.ui.show_error(f"Error processing {item_code}: {e}")
            self.state_manager.mark_failed(item_code, str(e))
            return False
    
    def run(self):
        """Main execution flow"""
        self.ui.show_info("Starting Shopify Product Uploader")
        
        # Validate settings
        try:
            settings.validate()
        except ValueError as e:
            self.ui.show_error(str(e))
            sys.exit(1)
        
        # Test connections
        if not self.test_connections():
            sys.exit(1)
        
        # Show current statistics
        stats = self.state_manager.get_statistics()
        if stats.get('total', 0) > 0:
            self.ui.show_info(f"Resuming from previous run: {stats}")
        
        # Process items
        uploaded_count = 0
        skipped_count = 0
        failed_count = 0
        
        try:
            # Get items based on mode
            if self.args.item_code:
                # Single item mode
                item = self.erpnext.get_item_by_code(self.args.item_code)
                if not item:
                    self.ui.show_error(f"Item {self.args.item_code} not found")
                    sys.exit(1)
                items = [item]
            else:
                # Batch mode
                items = self.erpnext.get_all_items(page_size=self.args.batch_size)
            
            for i, item in enumerate(items, 1):
                if self.args.limit and i > self.args.limit:
                    self.ui.show_info(f"Reached limit of {self.args.limit} items")
                    break
                
                self.ui.show_info(f"\n[{i}] Processing item: {item.item_code}")
                
                success = self.process_item(item)
                
                if success:
                    state = self.state_manager.get_product_state(item.item_code)
                    if state['status'] == ProcessStatus.UPLOADED.value:
                        uploaded_count += 1
                    else:
                        skipped_count += 1
                else:
                    failed_count += 1
                
                # Show running total
                total = uploaded_count + skipped_count + failed_count
                self.ui.show_info(
                    f"Progress: {uploaded_count} uploaded, "
                    f"{skipped_count} skipped, {failed_count} failed"
                )
        
        except KeyboardInterrupt:
            self.ui.show_warning("\nProcess interrupted by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            self.ui.show_error(f"Fatal error: {e}")
        
        # Show final summary
        self.ui.show_summary(uploaded_count, skipped_count, failed_count)
        
        # Export state for backup
        if self.args.export_state:
            export_path = Path(self.args.export_state)
            self.state_manager.export_to_jsonl(export_path)
            self.ui.show_info(f"State exported to {export_path}")

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Upload products from ERPNext to Shopify with SEO optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--item-code',
        help='Process a single item by code'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of items per batch (default: 100)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of items to process'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without actually uploading to Shopify'
    )
    
    parser.add_argument(
        '--default-price',
        help='Default price for auto-approval mode'
    )
    
    parser.add_argument(
        '--export-state',
        help='Export final state to JSONL file'
    )
    
    parser.add_argument(
        '--reset-item',
        help='Reset a specific item to pending status'
    )
    
    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear all cached images'
    )
    
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show statistics and exit'
    )
    
    args = parser.parse_args()
    
    # Handle special commands
    if args.stats:
        state_manager = StateManager()
        stats = state_manager.get_statistics()
        print("Processing Statistics:")
        for status, count in stats.items():
            print(f"  {status}: {count}")
        sys.exit(0)
    
    if args.reset_item:
        state_manager = StateManager()
        state_manager.reset_item(args.reset_item)
        print(f"Reset {args.reset_item} to pending")
        sys.exit(0)
    
    if args.clear_cache:
        image_manager = ImageManager()
        size, count = image_manager.get_cache_size()
        print(f"Cache size: {size:,} bytes in {count} files")
        confirm = input("Clear cache? [y/N]: ").strip().lower()
        if confirm in ['y', 'yes']:
            import shutil
            shutil.rmtree(settings.IMAGE_DIR)
            print("Cache cleared")
        sys.exit(0)
    
    # Run main application
    uploader = ProductUploader(args)
    uploader.run()

if __name__ == "__main__":
    main()