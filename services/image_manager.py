import os
import hashlib
import requests
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse, unquote
from config.settings import settings
from utils.logger import get_logger
from tenacity import retry, stop_after_attempt, wait_exponential

logger = get_logger(__name__)

class ImageManager:
    """Manages image downloading and caching with order preservation"""
    
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or settings.IMAGE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Image cache directory: {self.base_dir}")
    
    def get_item_image_dir(self, item_code: str) -> Path:
        """Get the image directory for a specific item"""
        item_dir = self.base_dir / item_code
        item_dir.mkdir(parents=True, exist_ok=True)
        return item_dir
    
    def get_image_filename(self, url: str, index: int) -> str:
        """Generate a filename for an image URL with index prefix for ordering"""
        # Try to extract original filename
        parsed = urlparse(url)
        path = unquote(parsed.path)
        original_name = os.path.basename(path)
        
        # Remove Shopify CDN parameters
        if original_name and '.' in original_name:
            name, ext = os.path.splitext(original_name)
            # Clean up name
            name = name.split('_')[0] if '_' in name else name
            # Use index prefix to maintain order (001, 002, etc.)
            return f"{index:03d}_{name[:50]}{ext}"
        
        # Fallback: use hash with index prefix
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return f"{index:03d}_image_{url_hash}.jpg"
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def download_image(self, url: str, save_path: Path) -> bool:
        """Download a single image"""
        try:
            headers = {
                'User-Agent': settings.USER_AGENT
            }
            
            response = requests.get(
                url,
                headers=headers,
                timeout=settings.SCRAPE_TIMEOUT,
                stream=True
            )
            response.raise_for_status()
            
            # Write image to file
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = save_path.stat().st_size
            logger.debug(f"Downloaded {save_path.name} ({file_size:,} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download image {url}: {e}")
            if save_path.exists():
                save_path.unlink()
            return False

    def download_image_for_item(self, url: str, item_code: str, filename: str) -> Optional[Path]:
        """Download a single image for an item with specified filename"""
        try:
            item_dir = self.get_item_image_dir(item_code)
            save_path = item_dir / filename
            
            # Check if already exists
            if save_path.exists():
                logger.debug(f"Image already exists: {save_path}")
                return save_path
            
            if self.download_image(url, save_path):
                logger.info(f"Downloaded image for {item_code}: {filename}")
                return save_path
            else:
                logger.error(f"Failed to download image for {item_code}: {filename}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading image for {item_code}: {e}")
            return None
    
    def download_product_images(self, item_code: str, image_urls: List[str]) -> List[Path]:
        """
        Download all images for a product, maintaining order.
        The first image in the list will be the primary image.
        """
        if not image_urls:
            logger.warning(f"No images to download for {item_code}")
            return []
        
        item_dir = self.get_item_image_dir(item_code)
        downloaded_files = []
        
        logger.info(f"Downloading {len(image_urls)} images for {item_code} (first will be primary)")
        
        for i, url in enumerate(image_urls):
            # Use 0-based index for filename to ensure proper sorting
            filename = self.get_image_filename(url, i)
            save_path = item_dir / filename
            
            # Skip if already downloaded
            if save_path.exists():
                logger.debug(f"Image already cached: {filename}")
                downloaded_files.append(save_path)
                continue
            
            # Download the image
            if self.download_image(url, save_path):
                downloaded_files.append(save_path)
                if i == 0:
                    logger.info(f"Downloaded primary image: {filename}")
            else:
                logger.warning(f"Skipping failed image download: {url}")
        
        logger.info(f"Downloaded {len(downloaded_files)}/{len(image_urls)} images for {item_code}")
        return downloaded_files
    
    def clear_item_cache(self, item_code: str) -> None:
        """Clear cached images for an item"""
        item_dir = self.get_item_image_dir(item_code)
        if item_dir.exists():
            for file in item_dir.iterdir():
                if file.is_file():
                    file.unlink()
            item_dir.rmdir()
            logger.info(f"Cleared image cache for {item_code}")
    
    def get_cached_images(self, item_code: str) -> List[Path]:
        """
        Get list of cached images for an item, sorted by filename.
        The first image in the returned list will be the primary image.
        """
        item_dir = self.get_item_image_dir(item_code)
        if not item_dir.exists():
            return []
        
        # Sort by filename to maintain order (000_*, 001_*, 002_*, etc.)
        images = sorted([
            f for f in item_dir.iterdir() 
            if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        ])
        
        if images:
            logger.debug(f"Found {len(images)} cached images, primary: {images[0].name}")
        
        return images
    
    def get_primary_image(self, item_code: str) -> Optional[Path]:
        """Get the primary (first) image for an item"""
        images = self.get_cached_images(item_code)
        return images[0] if images else None
    
    def get_cache_size(self) -> Tuple[int, int]:
        """Get total cache size and file count"""
        total_size = 0
        file_count = 0
        
        for item_dir in self.base_dir.iterdir():
            if item_dir.is_dir():
                for file in item_dir.iterdir():
                    if file.is_file():
                        total_size += file.stat().st_size
                        file_count += 1
        
        return total_size, file_count