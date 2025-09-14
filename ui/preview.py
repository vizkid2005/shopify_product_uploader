import os
import tempfile
import subprocess
from typing import List, Optional, Tuple
from pathlib import Path
from colorama import init, Fore, Style
from tabulate import tabulate
from utils.logger import get_logger

# Initialize colorama for cross-platform colored output
init(autoreset=True)

logger = get_logger(__name__)

class ProductPreview:
    """Interactive product preview and approval system"""
    
    def __init__(self):
        self.editor = os.environ.get('EDITOR', 'nano')
    
    def display_preview(self,
                       item_code: str,
                       title: str,
                       description_html: str,
                       image_files: List[Path],
                       competitor_url: str,
                       seo_title: Optional[str] = None,
                       meta_description: Optional[str] = None) -> None:
        """Display product preview to user"""
        
        print("\n" + "="*80)
        print(f"{Fore.CYAN}PRODUCT PREVIEW{Style.RESET_ALL}")
        print("="*80)
        
        # Basic info table
        info_data = [
            ["ERPNext Item Code", f"{Fore.YELLOW}{item_code}{Style.RESET_ALL}"],
            ["Product Title", f"{Fore.GREEN}{title}{Style.RESET_ALL}"],
            ["Source URL", competitor_url],
            ["Images", f"{len(image_files)} files"]
        ]
        
        # Add SEO info if available
        if seo_title:
            info_data.append(["SEO Title", f"{Fore.MAGENTA}{seo_title}{Style.RESET_ALL}"])
        if meta_description:
            # Truncate meta description for display
            meta_preview = meta_description[:60] + "..." if len(meta_description) > 60 else meta_description
            info_data.append(["Meta Description", f"{Fore.CYAN}{meta_preview}{Style.RESET_ALL}"])
        
        print(tabulate(info_data, tablefmt="plain"))
        print()
        
        # Show image filenames
        if image_files:
            print(f"{Fore.BLUE}Images:{Style.RESET_ALL}")
            for i, img_path in enumerate(image_files, 1):
                marker = "⭐" if i == 1 else "  "
                print(f"  {marker} {i}. {img_path.name}")
            print(f"  {Fore.YELLOW}⭐ = Primary image{Style.RESET_ALL}")
        print()
        
        # Show description preview (first 300 chars)
        print(f"{Fore.BLUE}Description Preview:{Style.RESET_ALL}")
        # Strip HTML tags for preview
        import re
        text_preview = re.sub('<[^<]+?>', '', description_html)[:300]
        print(f"  {text_preview}...")
        print()
    
    def get_approval_and_price(self) -> Tuple[bool, Optional[str]]:
        """Get user approval and price"""
        print(f"{Fore.YELLOW}Ready to upload to Shopify?{Style.RESET_ALL}")
        
        # Get approval
        while True:
            approval = input(f"  Approve upload? [y/N]: ").strip().lower()
            if approval in ['y', 'yes']:
                approved = True
                break
            elif approval in ['n', 'no', '']:
                logger.info("Product upload rejected by user")
                return False, None
            else:
                print(f"  {Fore.RED}Please enter 'y' for yes or 'n' for no{Style.RESET_ALL}")
        
        # Get price if approved
        if approved:
            while True:
                price_input = input(f"  Enter price (e.g., 19.99): ").strip()
                try:
                    # Validate price format
                    price = float(price_input)
                    if price <= 0:
                        print(f"  {Fore.RED}Price must be greater than 0{Style.RESET_ALL}")
                        continue
                    return True, f"{price:.2f}"
                except ValueError:
                    print(f"  {Fore.RED}Invalid price format. Please enter a number{Style.RESET_ALL}")
        
        return False, None
    
    def edit_description(self, description_html: str) -> str:
        """Allow user to edit description in their editor"""
        try:
            # Create temp file with current description
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(description_html)
                temp_path = f.name
            
            print(f"\n{Fore.CYAN}Opening editor ({self.editor})...{Style.RESET_ALL}")
            
            # Open editor
            subprocess.call([self.editor, temp_path])
            
            # Read edited content
            with open(temp_path, 'r') as f:
                edited_description = f.read()
            
            # Clean up
            os.unlink(temp_path)
            
            if edited_description != description_html:
                logger.info("Description edited by user")
            
            return edited_description
            
        except Exception as e:
            logger.error(f"Error editing description: {e}")
            return description_html
    
    def ask_edit_description(self) -> bool:
        """Ask if user wants to edit the description"""
        response = input(f"  Edit description before upload? [y/N]: ").strip().lower()
        return response in ['y', 'yes']
    
    def show_summary(self, 
                    uploaded_count: int,
                    skipped_count: int,
                    failed_count: int) -> None:
        """Show final summary"""
        print("\n" + "="*80)
        print(f"{Fore.CYAN}UPLOAD SUMMARY{Style.RESET_ALL}")
        print("="*80)
        
        summary_data = [
            ["Uploaded", f"{Fore.GREEN}{uploaded_count}{Style.RESET_ALL}"],
            ["Skipped", f"{Fore.YELLOW}{skipped_count}{Style.RESET_ALL}"],
            ["Failed", f"{Fore.RED}{failed_count}{Style.RESET_ALL}"],
            ["Total", uploaded_count + skipped_count + failed_count]
        ]
        
        print(tabulate(summary_data, tablefmt="plain"))
        print()
    
    def show_error(self, message: str) -> None:
        """Display error message"""
        print(f"{Fore.RED}❌ ERROR: {message}{Style.RESET_ALL}")
    
    def show_success(self, message: str) -> None:
        """Display success message"""
        print(f"{Fore.GREEN}✅ {message}{Style.RESET_ALL}")
    
    def show_info(self, message: str) -> None:
        """Display info message"""
        print(f"{Fore.BLUE}ℹ️  {message}{Style.RESET_ALL}")
    
    def show_warning(self, message: str) -> None:
        """Display warning message"""
        print(f"{Fore.YELLOW}⚠️  {message}{Style.RESET_ALL}")