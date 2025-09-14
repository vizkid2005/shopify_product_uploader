from typing import Dict, List, Any, Optional
from utils.logger import get_logger
from tenacity import retry, stop_after_attempt, wait_exponential
from .graphql import GraphQLExecutor

logger = get_logger(__name__)

class ShopifyValidation:
    """Handles validation and setup of required Shopify fields and metafields"""
    
    def __init__(self, graphql_executor: GraphQLExecutor):
        self.graphql = graphql_executor
        self._validated_metafields = set()
        
    def ensure_required_setup(self) -> Dict[str, Any]:
        """
        Ensure all required metafield definitions and custom fields exist.
        Returns a validation report.
        """
        validation_report = {
            "metafields": {},
            "success": True,
            "errors": []
        }
        
        try:
            # Validate metafield definitions
            metafield_result = self._ensure_metafield_definitions()
            validation_report["metafields"] = metafield_result
            
            if not metafield_result.get("success", False):
                validation_report["success"] = False
                validation_report["errors"].extend(metafield_result.get("errors", []))
                
        except Exception as e:
            logger.error(f"Error during Shopify validation setup: {e}")
            validation_report["success"] = False
            validation_report["errors"].append(f"Setup failed: {str(e)}")
            
        return validation_report
    
    def _ensure_metafield_definitions(self) -> Dict[str, Any]:
        """
        Ensure required metafield definitions exist in Shopify.
        Creates them if they don't exist.
        """
        result = {
            "success": True,
            "errors": [],
            "created": [],
            "existing": []
        }
        
        required_metafields = [
            {
                "namespace": "erpnext",
                "key": "item_code",
                "name": "ERPNext Item Code",
                "description": "The item code from ERPNext system for product tracking",
                "type": "single_line_text_field",
                "owner_type": "PRODUCT"
            }
        ]
        
        for metafield_def in required_metafields:
            try:
                metafield_key = f"{metafield_def['namespace']}.{metafield_def['key']}"
                
                # Skip if already validated in this session
                if metafield_key in self._validated_metafields:
                    result["existing"].append(metafield_key)
                    continue
                
                # Check if metafield definition exists
                existing = self._get_metafield_definition(
                    metafield_def["namespace"], 
                    metafield_def["key"], 
                    metafield_def["owner_type"]
                )
                
                if existing:
                    logger.info(f"Metafield definition exists: {metafield_key}")
                    result["existing"].append(metafield_key)
                    self._validated_metafields.add(metafield_key)
                else:
                    # Create the metafield definition
                    created = self._create_metafield_definition(metafield_def)
                    if created:
                        logger.info(f"Created metafield definition: {metafield_key}")
                        result["created"].append(metafield_key)
                        self._validated_metafields.add(metafield_key)
                    else:
                        error_msg = f"Failed to create metafield definition: {metafield_key}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
                        result["success"] = False
                        
            except Exception as e:
                error_msg = f"Error handling metafield {metafield_def['namespace']}.{metafield_def['key']}: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
                result["success"] = False
        
        return result
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _get_metafield_definition(self, namespace: str, key: str, owner_type: str) -> Optional[Dict[str, Any]]:
        """Check if a metafield definition exists"""
        query = """
        query getMetafieldDefinitions($namespace: String!, $key: String!, $ownerType: MetafieldOwnerType!) {
            metafieldDefinitions(first: 1, namespace: $namespace, key: $key, ownerType: $ownerType) {
                edges {
                    node {
                        id
                        namespace
                        key
                        name
                        description
                        type {
                            name
                        }
                        ownerType
                    }
                }
            }
        }
        """
        
        variables = {
            "namespace": namespace,
            "key": key,
            "ownerType": owner_type
        }
        
        result = self.graphql.execute(query, variables)
        if not result:
            return None
        
        definitions = result.get('metafieldDefinitions', {}).get('edges', [])
        if definitions:
            return definitions[0]['node']
        
        return None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _create_metafield_definition(self, metafield_def: Dict[str, Any]) -> bool:
        """Create a metafield definition in Shopify"""
        mutation = """
        mutation metafieldDefinitionCreate($definition: MetafieldDefinitionInput!) {
            metafieldDefinitionCreate(definition: $definition) {
                createdDefinition {
                    id
                    namespace
                    key
                    name
                    type {
                        name
                    }
                }
                userErrors {
                    field
                    message
                    code
                }
            }
        }
        """
        
        definition_input = {
            "namespace": metafield_def["namespace"],
            "key": metafield_def["key"],
            "name": metafield_def["name"],
            "description": metafield_def["description"],
            "type": metafield_def["type"],
            "ownerType": metafield_def["owner_type"]
        }
        
        variables = {"definition": definition_input}
        
        result = self.graphql.execute(mutation, variables)
        if not result:
            return False
        
        create_result = result.get('metafieldDefinitionCreate', {})
        
        # Check for user errors
        user_errors = create_result.get('userErrors', [])
        if user_errors:
            logger.error(f"Metafield definition creation errors: {user_errors}")
            return False
        
        # Check if definition was created
        created_definition = create_result.get('createdDefinition')
        if created_definition:
            logger.info(f"Successfully created metafield definition: {created_definition['namespace']}.{created_definition['key']}")
            return True
        
        return False
    
    def validate_product_fields(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that all required product fields are present and properly formatted.
        """
        validation_result = {
            "success": True,
            "errors": [],
            "warnings": []
        }
        
        # Required fields
        required_fields = ["title", "handle", "descriptionHtml"]
        for field in required_fields:
            if not product_data.get(field):
                validation_result["errors"].append(f"Missing required field: {field}")
                validation_result["success"] = False
        
        # Validate handle format (Shopify requirements)
        handle = product_data.get("handle", "")
        if handle:
            # Handle should be lowercase, alphanumeric with hyphens
            import re
            if not re.match(r'^[a-z0-9\-]+$', handle):
                validation_result["warnings"].append(f"Handle '{handle}' may not meet Shopify requirements (lowercase, alphanumeric, hyphens only)")
        
        # Validate metafields structure
        metafields = product_data.get("metafields", [])
        for metafield in metafields:
            if not all(key in metafield for key in ["namespace", "key", "value", "type"]):
                validation_result["errors"].append("Metafield missing required fields: namespace, key, value, type")
                validation_result["success"] = False
        
        # Validate SEO fields if present
        seo = product_data.get("seo", {})
        if seo:
            if seo.get("title") and len(seo["title"]) > 70:
                validation_result["warnings"].append("SEO title exceeds recommended 70 character limit")
            if seo.get("description") and len(seo["description"]) > 160:
                validation_result["warnings"].append("Meta description exceeds recommended 160 character limit")
        
        return validation_result
    
    def validate_variant_fields(self, variant_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate variant fields for product creation/update.
        """
        validation_result = {
            "success": True,
            "errors": [],
            "warnings": []
        }
        
        # Validate price
        price = variant_data.get("price")
        if price is not None:
            try:
                price_float = float(price)
                if price_float < 0:
                    validation_result["errors"].append("Price cannot be negative")
                    validation_result["success"] = False
            except (ValueError, TypeError):
                validation_result["errors"].append("Invalid price format")
                validation_result["success"] = False
        
        return validation_result