import requests
from typing import Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import get_logger

logger = get_logger(__name__)

class GraphQLExecutor:
    """Handles GraphQL query execution and common GraphQL operations"""
    
    def __init__(self, graphql_url: str, headers: Dict[str, str]):
        self.graphql_url = graphql_url
        self.headers = headers
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def execute(self, query: str, variables: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Execute a GraphQL query against Shopify Admin API"""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        try:
            response = requests.post(
                self.graphql_url,
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            
            data = response.json()
            if 'errors' in data:
                logger.error(f"GraphQL errors: {data['errors']}")
                return None
            
            return data.get('data')
            
        except Exception as e:
            logger.error(f"GraphQL request failed: {e}")
            return None