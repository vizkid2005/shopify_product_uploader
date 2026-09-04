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
        
        prompt = f"""
You are an expert e-commerce SEO copywriter who deeply understands how Gen-Z and Millennial shoppers think, read, and make purchase decisions.
Create high-converting, search-optimized content for the product below.

Product Name: {product_name}
SEO Title: {seo_title}
Original Description:
{original_description}

Create the following output:

SEO-optimized product description in clean HTML

Meta description for search results (160 characters max)

HTML Description Requirements

Use only these tags: <h2>, <h3>, <p>, <ul>, <li>, <strong>, <em> — never <h1>

The first section must be a short description of the scent.

The second section must always present the fragrance structure in this exact order with heading as Fragrance Notes:

Top Notes

Middle Notes

Base Notes

(Each must be its own clearly separated block.)

The Third section must include SEO keyword related sentences.

Write in a youthful, engaging, confidence-boosting tone that resonates with shoppers under 40.

Keep it concise but complete (ideal length: 100–200 words).

Format for mobile-first readability using short paragraphs and scannable structure.

Include relevant keywords naturally for stronger SEO.

Use semantic HTML for clearer search engine interpretation.
"""

        try:
            logger.info(f"Optimizing content for: {product_name}")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert e-commerce SEO copywriter. You output only JSON content without the ``` enclosing tags. Return description_html and meta_description"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=2500,
                temperature=0.85
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                print(content)
                seo_content = json.loads(content)
                # Validate required keys
                required_keys = ['description_html', 'meta_description']
                if not all(key in seo_content for key in required_keys):
                    logger.error("Missing keys in AI response")
                    raise ValueError(f"AI response missing required keys. Expected: {required_keys}, Got: {list(seo_content.keys())}")

                # Basic validation
                if not seo_content['description_html'] or '<' not in seo_content['description_html']:
                    logger.error("Invalid HTML in AI response")
                    raise ValueError(f"AI response contains invalid HTML: {seo_content['description_html'][:100]}")

                # Add the SEO title to the response
                seo_content['seo_title'] = seo_title

                logger.info(f"Successfully optimized content for {item_code}")
                return seo_content

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response from AI: {e}")
                raise ValueError(f"AI returned invalid JSON: {content[:200]}") from e

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

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