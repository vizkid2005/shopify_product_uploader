from typing import Optional, Dict, Any, List
from openai import OpenAI
from config.settings import settings
from utils.logger import get_logger
from tenacity import retry, stop_after_attempt, wait_exponential
import json

logger = get_logger(__name__)

class SEOOptimizer:
    """Optimize product descriptions using OpenAI ChatGPT API"""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")
        
        self.client = OpenAI(api_key=self.api_key)
        logger.info(f"Initialized ChatGPT SEO optimizer with model: {self.model}")
    
    def create_seo_title(self, title_parts: List[str], max_length: int = 60) -> str:
        """Create SEO title from parts using | separator, respecting length limit"""
        if not title_parts:
            return "Premium Fragrance"
        
        # Start with the product name (first part)
        seo_title = title_parts[0]
        
        # Add other parts if they fit within the limit
        for part in title_parts[1:]:
            potential_title = f"{seo_title} | {part}"
            if len(potential_title) <= max_length:
                seo_title = potential_title
            else:
                break  # Stop adding parts if we exceed the limit
        
        return seo_title[:max_length].strip()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def optimize_content(self, 
                        product_name: str,
                        original_description: str,
                        item_code: str,
                        title_parts: Optional[List[str]] = None) -> Dict[str, str]:
        """
        Optimize product content for SEO including description, title, and meta description
        Returns dict with 'description_html', 'seo_title', 'meta_description'
        """
        if not original_description:
            original_description = "No description available"
        
        # Create SEO title from provided parts or fallback to product name
        if title_parts:
            seo_title = self.create_seo_title(title_parts)
        else:
            seo_title = self.create_seo_title([product_name])
        
        prompt = f"""You are an expert e-commerce SEO copywriter. Create comprehensive SEO content for this product that will rank well and convert visitors.

Product Name: {product_name}
SEO Title: {seo_title}
SKU/Item Code: {item_code}
Original Description:
{original_description}

Create the following content:

1. SEO-optimized product description in HTML format
2. Meta description for search results (max 160 characters)

Requirements for description HTML:
- Use proper HTML tags (h2, h3, p, ul, li, strong, em) - NO h1 tag
- Include relevant keywords naturally throughout
- Structure content with clear sections including Top Notes, Middle Notes and Base Notes if applicable
- Write in an engaging, professional tone that builds trust
- Keep it concise but comprehensive (300-500 words ideal)
- Ensure mobile-friendly formatting with short paragraphs
- Use semantic HTML for better SEO

Requirements for meta description:
- Summarize key benefits and features
- Include a call to action
- Stay under 160 characters
- Be compelling for search results

Return your response as a JSON object with these exact keys:
{{"description_html": "...", "meta_description": "..."}}

Output only the JSON, no additional text or explanations.

Don't even enclose the json in surrounding json block. Just start with the opening bracket directly
"""

        try:
            logger.info(f"Optimizing content for: {product_name}")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert e-commerce SEO copywriter. You output only JSON content."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=2500,
                temperature=0.7
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                print(content)
                seo_content = json.loads(content)
                # Validate required keys
                required_keys = ['description_html', 'meta_description']
                if not all(key in seo_content for key in required_keys):
                    logger.warning("Missing keys in AI response, using fallback")
                    return self._create_fallback_content(product_name, original_description, seo_title)
                
                # Basic validation
                if not seo_content['description_html'] or '<' not in seo_content['description_html']:
                    logger.warning("Invalid HTML in AI response, using fallback")
                    return self._create_fallback_content(product_name, original_description, seo_title)
                
                # Add the SEO title to the response
                seo_content['seo_title'] = seo_title
                
                logger.info(f"Successfully optimized content for {item_code}")
                return seo_content
                
            except json.JSONDecodeError:
                logger.warning("Invalid JSON response from AI, using fallback")
                return self._create_fallback_content(product_name, original_description, seo_title)
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return self._create_fallback_content(product_name, original_description, seo_title)
    
    def _create_fallback_content(self, product_name: str, description: str, seo_title: str) -> Dict[str, str]:
        """Create fallback content if ChatGPT API fails"""
        logger.info("Using fallback content generation")
        
        # Clean up description
        description = description.strip() if description else f"Discover the exceptional quality of {product_name}"
        
        # Basic HTML structure
        html = f"""
<div class="product-description">
    <h2>About {product_name}</h2>
    <p>{description}</p>
    
    <h3>Why Choose This Product?</h3>
    <ul>
        <li>Alcohol-free</li>
        <li>High-Quality Product from the heart of the Middle East</li>
        <li>Exceptional value</li>
        <li>Fast, reliable shipping</li>
    </ul>
    
    <p><strong>Order {product_name} today as a gift for yourself or a loved one.</strong></p>
</div>
""".strip()
        
        # Create fallback meta description
        meta_description = f"Shop {product_name} Premium quality fragrance. Alcohol-free. Proudly Canadian. Shipping to only Canadians."
        if len(meta_description) > 160:
            meta_description = meta_description[:157] + "..."
        
        return {
            "description_html": html,
            "seo_title": seo_title,
            "meta_description": meta_description
        }

    def _create_fallback_html(self, product_name: str, description: str) -> str:
        """Create basic HTML if ChatGPT API fails (legacy method)"""
        content = self._create_fallback_content(product_name, description, product_name)
        return content["description_html"]
    
    def test_connection(self) -> bool:
        """Test the OpenAI API connection"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": "Say 'OK'"
                    }
                ],
                max_tokens=10
            )
            logger.info("OpenAI API connection test successful")
            return True
        except Exception as e:
            logger.error(f"OpenAI API connection test failed: {e}")
            return False