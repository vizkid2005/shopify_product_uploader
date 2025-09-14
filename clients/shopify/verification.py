from typing import Dict, Any
from utils.logger import get_logger
from .graphql import GraphQLExecutor

logger = get_logger(__name__)

class APIVerification:
    """Handles Shopify API access verification and permission checking"""
    
    def __init__(self, graphql_executor: GraphQLExecutor, api_version: str, graphql_url: str, store: str):
        self.graphql = graphql_executor
        self.api_version = api_version
        self.graphql_url = graphql_url
        self.store = store
    
    def verify_access(self) -> Dict[str, Any]:
        """
        Verify GraphQL API access and required permissions.
        Returns detailed verification results including permissions and API limits.
        """
        verification_result = {
            "connected": False,
            "shop_info": {},
            "permissions": {
                "read_products": False,
                "write_products": False,
                "read_files": False,
                "write_files": False
            },
            "api_info": {},
            "errors": []
        }
        
        # Step 1: Test basic connection and shop info
        logger.info("Verifying Shopify GraphQL API access...")
        
        shop_query = """
        query {
            shop {
                name
                myshopifyDomain
                email
                plan {
                    displayName
                    partnerDevelopment
                }
                currencyCode
            }
        }
        """
        
        try:
            result = self.graphql.execute(shop_query)
            if result and result.get('shop'):
                shop = result['shop']
                verification_result["connected"] = True
                verification_result["shop_info"] = shop
                
                logger.info(f"✓ Connected to Shopify store: {shop.get('name')} ({shop.get('myshopifyDomain')})")
                logger.info(f"✓ Plan: {shop.get('plan', {}).get('displayName', 'Unknown')}")
                logger.info(f"✓ Currency: {shop.get('currencyCode', 'Unknown')}")
            else:
                verification_result["errors"].append("Failed to retrieve shop information")
                logger.error("✗ Failed to retrieve shop information")
                return verification_result
                
        except Exception as e:
            error_msg = f"Shop query failed: {str(e)}"
            verification_result["errors"].append(error_msg)
            logger.error(f"✗ {error_msg}")
            return verification_result
        
        # Step 2: Test read_products permission
        logger.info("Testing read_products permission...")
        products_query = """
        query {
            products(first: 1) {
                edges {
                    node {
                        id
                        title
                        handle
                    }
                }
            }
        }
        """
        
        try:
            result = self.graphql.execute(products_query)
            if result and 'products' in result:
                verification_result["permissions"]["read_products"] = True
                logger.info("✓ read_products permission verified")
            else:
                verification_result["errors"].append("read_products permission denied or failed")
                logger.error("✗ read_products permission denied or failed")
        except Exception as e:
            error_msg = f"Products read test failed: {str(e)}"
            verification_result["errors"].append(error_msg)
            logger.error(f"✗ {error_msg}")
        
        # Step 3: Test write_products permission (using a safe query that doesn't modify data)
        logger.info("Testing write_products permission...")
        # We'll test this by trying to access product creation fields in introspection
        introspection_query = """
        query {
            __type(name: "Mutation") {
                fields(includeDeprecated: false) {
                    name
                    description
                }
            }
        }
        """
        
        mutation_fields = []
        try:
            result = self.graphql.execute(introspection_query)
            if result and result.get('__type', {}).get('fields'):
                mutation_fields = [field['name'] for field in result['__type']['fields']]
                if 'productCreate' in mutation_fields and 'productUpdate' in mutation_fields:
                    verification_result["permissions"]["write_products"] = True
                    logger.info("✓ write_products permission verified (productCreate/productUpdate available)")
                else:
                    verification_result["errors"].append("write_products permission denied - product mutations not available")
                    logger.error("✗ write_products permission denied - product mutations not available")
            else:
                verification_result["errors"].append("Could not verify write_products permission")
                logger.error("✗ Could not verify write_products permission")
        except Exception as e:
            error_msg = f"Mutation introspection failed: {str(e)}"
            verification_result["errors"].append(error_msg)
            logger.error(f"✗ {error_msg}")
        
        # Step 4: Test file upload permissions
        logger.info("Testing file upload permissions...")
        files_query = """
        query {
            files(first: 1) {
                edges {
                    node {
                        id
                        alt
                    }
                }
            }
        }
        """
        
        try:
            result = self.graphql.execute(files_query)
            if result and 'files' in result:
                verification_result["permissions"]["read_files"] = True
                logger.info("✓ read_files permission verified")
                
                # Check for staged upload mutations
                if 'stagedUploadsCreate' in mutation_fields:
                    verification_result["permissions"]["write_files"] = True
                    logger.info("✓ write_files permission verified (stagedUploadsCreate available)")
                else:
                    verification_result["errors"].append("write_files permission denied - stagedUploadsCreate not available")
                    logger.error("✗ write_files permission denied - stagedUploadsCreate not available")
            else:
                verification_result["errors"].append("read_files permission denied or failed")
                logger.error("✗ read_files permission denied or failed")
        except Exception as e:
            error_msg = f"Files read test failed: {str(e)}"
            verification_result["errors"].append(error_msg)
            logger.error(f"✗ {error_msg}")
        
        # Step 5: Get API version and rate limit info
        logger.info("Checking API version and limits...")
        try:
            verification_result["api_info"] = {
                "api_version": self.api_version,
                "graphql_url": self.graphql_url,
                "store_domain": self.store
            }
            logger.info(f"✓ API Version: {self.api_version}")
            logger.info(f"✓ GraphQL Endpoint: {self.graphql_url}")
        except Exception as e:
            error_msg = f"API info gathering failed: {str(e)}"
            verification_result["errors"].append(error_msg)
            logger.error(f"✗ {error_msg}")
        
        # Summary
        required_permissions = ['read_products', 'write_products', 'write_files']
        missing_permissions = [perm for perm in required_permissions 
                             if not verification_result["permissions"][perm]]
        
        if verification_result["connected"] and not missing_permissions:
            logger.info("🎉 GraphQL API verification successful! All required permissions available.")
        else:
            if missing_permissions:
                logger.error(f"❌ Missing required permissions: {', '.join(missing_permissions)}")
                verification_result["errors"].append(f"Missing permissions: {', '.join(missing_permissions)}")
            if not verification_result["connected"]:
                logger.error("❌ Failed to establish GraphQL connection")
        
        return verification_result
    
    def test_connection(self) -> bool:
        """Test the connection to Shopify using GraphQL (legacy method)"""
        verification = self.verify_access()
        return verification["connected"] and len(verification["errors"]) == 0
    
    def verify_or_raise(self) -> None:
        """
        Verify GraphQL access and raise exceptions if there are critical issues.
        Use this method when you want to fail fast on connection/permission problems.
        """
        verification = self.verify_access()
        
        if not verification["connected"]:
            raise ConnectionError(f"Failed to connect to Shopify GraphQL API: {'; '.join(verification['errors'])}")
        
        # Check for critical missing permissions
        critical_permissions = ['read_products', 'write_products']
        missing_critical = [perm for perm in critical_permissions 
                          if not verification["permissions"][perm]]
        if missing_critical:
            raise PermissionError(f"Missing critical Shopify permissions: {', '.join(missing_critical)}")
        
        logger.info("✅ Shopify GraphQL API access verified successfully")