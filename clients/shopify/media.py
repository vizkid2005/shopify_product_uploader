import mimetypes
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import get_logger
from .graphql import GraphQLExecutor

logger = get_logger(__name__)

class MediaManager:
    """Handles file uploads and media operations for Shopify products"""
    
    def __init__(self, graphql_executor: GraphQLExecutor):
        self.graphql = graphql_executor
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def stage_file_upload(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Stage a file for upload using stagedUploadsCreate mutation.
        Returns the staged target information for uploading.
        """
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None
        
        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "image/jpeg"  # Default fallback
        
        # GraphQL mutation to create staged upload
        mutation = """
        mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
            stagedUploadsCreate(input: $input) {
                stagedTargets {
                    url
                    resourceUrl
                    parameters {
                        name
                        value
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        
        variables = {
            "input": [{
                "filename": file_path.name,
                "mimeType": mime_type,
                "httpMethod": "POST",
                "resource": "IMAGE"
            }]
        }
        
        result = self.graphql.execute(mutation, variables)
        logger.info(result)
        logger.info(variables)
        if not result:
            return None
        
        staged_uploads = result.get('stagedUploadsCreate', {})
        if staged_uploads.get('userErrors'):
            logger.error(f"Staged upload errors: {staged_uploads['userErrors']}")
            return None
        
        staged_targets = staged_uploads.get('stagedTargets', [])
        if not staged_targets:
            logger.error("No staged targets returned")
            return None
        
        return staged_targets[0]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def upload_file_to_staged_target(self, file_path: Path, staged_target: Dict[str, Any]) -> bool:
        """Upload a file to the staged target URL returned by stagedUploadsCreate."""
        upload_url = staged_target.get('url')
        parameters = staged_target.get('parameters', [])
        
        # Convert parameters list to dict
        form_data = {param['name']: param['value'] for param in parameters}
        logger.info("Form Data")
        logger.info(form_data)
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (file_path.name, f)}
                
                response = requests.post(
                    upload_url,
                    data=form_data,
                    files=files
                )
                logger.info("Upload Response")
                logger.info(response)
                response.raise_for_status()
                
                logger.info(f"Successfully uploaded {file_path.name} to staged target")
                return True
                
        except Exception as e:
            logger.error(f"Failed to upload {file_path.name}: {e}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_product_with_media(self, product_data: Dict[str, Any], image_paths: List[Path], synchronous: bool = True) -> Optional[Dict[str, Any]]:
        """
        Create a new product with media using the modern productSet mutation.
        Returns the created product data.
        """
        if not image_paths:
            logger.warning("No image paths provided for product creation")
            return None

        # Prepare media files for productSet
        files = []
        for image_path in image_paths:
            if not image_path.exists():
                logger.warning(f"Image file not found: {image_path}")
                continue

            # Stage the upload
            staged_target = self.stage_file_upload(image_path)
            if not staged_target:
                logger.error(f"Failed to stage upload for {image_path.name}")
                continue

            # Upload file to staged target
            if not self.upload_file_to_staged_target(image_path, staged_target):
                logger.error(f"Failed to upload {image_path.name}")
                continue

            files.append({
                "originalSource": staged_target.get('resourceUrl'),
                "alt": product_data.get('title', f"Product image: {image_path.stem}"),
                "filename": image_path.name,
                "contentType": "IMAGE"
            })

        if not files:
            logger.error("No files were successfully staged for upload")
            return None

        # Create product with media using productSet
        mutation = """
        mutation productSet($input: ProductSetInput!, $synchronous: Boolean!) {
            productSet(input: $input, synchronous: $synchronous) {
                product {
                    id
                    handle
                    title
                    description
                    media(first: 20) {
                        nodes {
                            id
                            alt
                            mediaContentType
                            status
                        }
                    }
                }
                productSetOperation {
                    id
                    status
                }
                userErrors {
                    code
                    field
                    message
                }
            }
        }
        """

        # Merge product data with files
        product_input = {**product_data, "files": files}

        variables = {
            "input": product_input,
            "synchronous": synchronous
        }

        result = self.graphql.execute(mutation, variables)
        if result:
            product_set_result = result.get('productSet', {})
            logger.info(product_set_result)
            if product_set_result.get('userErrors'):
                logger.error(f"Product creation errors: {product_set_result['userErrors']}")
                return None
            else:
                product = product_set_result.get('product')
                if product:
                    logger.info(f"Successfully created product: {product.get('title')} with {len(files)} media files")
                    return product

        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def update_product_media(self, product_id: str, image_paths: List[Path], product_title: str = None) -> List[Dict[str, Any]]:
        """
        Update existing product with new media using the modern productUpdate mutation.
        Returns list of updated media objects.
        """
        if not image_paths:
            logger.warning("No image paths provided for product media update")
            return []

        # Prepare media for productUpdate
        media = []
        for image_path in image_paths:
            if not image_path.exists():
                logger.warning(f"Image file not found: {image_path}")
                continue

            # Stage the upload
            staged_target = self.stage_file_upload(image_path)
            if not staged_target:
                logger.error(f"Failed to stage upload for {image_path.name}")
                continue

            # Upload file to staged target
            if not self.upload_file_to_staged_target(image_path, staged_target):
                logger.error(f"Failed to upload {image_path.name}")
                continue

            media.append({
                "originalSource": staged_target.get('resourceUrl'),
                "alt": product_title or f"Product image: {image_path.stem}",
                "mediaContentType": "IMAGE"
            })

        if not media:
            logger.error("No media files were successfully staged for upload")
            return []

        # Update product with new media
        mutation = """
        mutation productUpdate($product: ProductUpdateInput!, $media: [CreateMediaInput!]) {
            productUpdate(product: $product, media: $media) {
                product {
                    id
                    media(first: 20) {
                        nodes {
                            id
                            alt
                            mediaContentType
                            status
                        }
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """

        variables = {
            "product": {"id": product_id},
            "media": media
        }

        result = self.graphql.execute(mutation, variables)
        if result:
            product_update_result = result.get('productUpdate', {})
            if product_update_result.get('userErrors'):
                logger.error(f"Product update errors: {product_update_result['userErrors']}")
                return []
            else:
                updated_media = product_update_result.get('product', {}).get('media', {}).get('nodes', [])
                logger.info(f"Successfully updated product {product_id} with {len(media)} media files")
                return updated_media

        return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def upload_product_media(self, product_id: str, image_paths: List[Path], product_title: str = None) -> List[Dict[str, Any]]:
        """
        Upload media files for a product. Uses productUpdate for existing products.
        Returns list of created/updated media objects.

        This method maintains backwards compatibility while using modern Shopify APIs.
        """
        return self.update_product_media(product_id, image_paths, product_title)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def delete_existing_media(self, product_id: str) -> bool:
        """Delete all existing media from a product to replace with new images."""
        # First, get all existing media
        query = """
        query getProductMedia($id: ID!) {
            product(id: $id) {
                media(first: 250) {
                    edges {
                        node {
                            id
                            mediaContentType
                        }
                    }
                }
            }
        }
        """
        
        result = self.graphql.execute(query, {"id": product_id})
        if not result:
            return False
        
        product = result.get('product')
        if not product:
            return False
        
        media_edges = product.get('media', {}).get('edges', [])
        if not media_edges:
            logger.info("No existing media to delete")
            return True
        
        # Delete each media item
        for media_edge in media_edges:
            media_id = media_edge['node']['id']
            
            delete_mutation = """
            mutation productDeleteMedia($productId: ID!, $mediaIds: [ID!]!) {
                productDeleteMedia(productId: $productId, mediaIds: $mediaIds) {
                    deletedMediaIds
                    deletedProductImageIds
                    mediaUserErrors {
                        field
                        message
                    }
                }
            }
            """
            
            delete_result = self.graphql.execute(delete_mutation, {
                "productId": product_id,
                "mediaIds": [media_id]
            })
            
            if delete_result:
                delete_media_result = delete_result.get('productDeleteMedia', {})
                if delete_media_result.get('mediaUserErrors'):
                    logger.error(f"Error deleting media {media_id}: {delete_media_result['mediaUserErrors']}")
                else:
                    logger.info(f"Deleted existing media: {media_id}")

        return True

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def replace_product_media(self, product_id: str, image_paths: List[Path], product_title: str = None) -> List[Dict[str, Any]]:
        """
        Replace all existing media for a product with new images.
        This is more efficient than delete + create as it does both in one operation.
        """
        if not image_paths:
            logger.warning("No image paths provided for media replacement")
            return []

        # First delete existing media
        if not self.delete_existing_media(product_id):
            logger.warning("Failed to delete existing media, proceeding with update anyway")

        # Then add new media
        return self.update_product_media(product_id, image_paths, product_title)

    def get_product_media(self, product_id: str) -> List[Dict[str, Any]]:
        """
        Get all media for a product.
        Returns list of media objects.
        """
        query = """
        query getProductMedia($id: ID!) {
            product(id: $id) {
                media(first: 250) {
                    edges {
                        node {
                            id
                            alt
                            mediaContentType
                            status
                            ... on MediaImage {
                                image {
                                    url
                                    width
                                    height
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        result = self.graphql.execute(query, {"id": product_id})
        if not result:
            return []

        product = result.get('product')
        if not product:
            return []

        media_edges = product.get('media', {}).get('edges', [])
        return [edge['node'] for edge in media_edges]