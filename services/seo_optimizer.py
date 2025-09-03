from typing import Optional
from openai import OpenAI
from config.settings import settings
from utils.logger import get_logger
from tenacity import retry, stop_after_attempt, wait_exponential

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
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def optimize_description(self, 
                           product_name: str,
                           original_description: str,
                           item_code: str) -> str:
        """
        Optimize product description for SEO and convert to Shopify-ready HTML
        """
        if not original_description:
            original_description = "No description available"
        
        prompt = f"""You are an expert e-commerce SEO copywriter. Transform the following product description into SEO-optimized, Shopify-ready HTML that will rank well and convert visitors into buyers.

Product Name: {product_name}
SKU/Item Code: {item_code}
Original Description:
{original_description}

Requirements:
1. Create compelling, SEO-friendly product description HTML
2. Use proper HTML tags (h2, h3, p, ul, li, strong, em) - NO h1 tag
3. Include relevant keywords naturally throughout
4. Structure content with clear sections (Features, Benefits, Specifications if applicable)
5. Write in an engaging, professional tone that builds trust
6. Keep it concise but comprehensive (300-500 words ideal)
7. Include a subtle call-to-action at the end
8. Ensure mobile-friendly formatting with short paragraphs
9. Use semantic HTML for better SEO

Output only the HTML content, no markdown or explanations. Start directly with the HTML tags."""

        try:
            logger.info(f"Optimizing description for: {product_name}")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert e-commerce SEO copywriter. You output only HTML content."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=2000,
                temperature=0.7
            )
            
            optimized_html = response.choices[0].message.content.strip()
            
            # Basic validation
            if not optimized_html or '<' not in optimized_html:
                logger.warning("Invalid HTML response from ChatGPT, using fallback")
                return self._create_fallback_html(product_name, original_description)
            
            logger.info(f"Successfully optimized description for {item_code}")
            return optimized_html
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return self._create_fallback_html(product_name, original_description)
    
    def _create_fallback_html(self, product_name: str, description: str) -> str:
        """Create basic HTML if ChatGPT API fails"""
        logger.info("Using fallback HTML generation")
        
        # Clean up description
        description = description.strip() if description else f"Discover the exceptional quality of {product_name}"
        
        # Basic HTML structure
        html = f"""
<div class="product-description">
    <h2>About {product_name}</h2>
    <p>{description}</p>
    
    <h3>Why Choose This Product?</h3>
    <ul>
        <li>Premium quality construction</li>
        <li>Carefully selected materials</li>
        <li>Exceptional value</li>
        <li>Fast, reliable shipping</li>
    </ul>
    
    <p><strong>Order your {product_name} today and experience the difference quality makes.</strong></p>
</div>
""".strip()
        
        return html
    
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