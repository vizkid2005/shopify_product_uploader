"""
Pricing Service - Handles competitor price scraping and Shopify price updates

This module provides:
1. Scraping prices from competitor websites
2. Updating ERPNext price lists with competitor prices
3. Syncing ERPNext prices to Shopify stores
"""

import re
from typing import Optional, Dict, Any
import requests
from utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


class PricingService:
    """Service for managing product pricing across competitors and Shopify"""

    def __init__(self, erpnext_client, shopify_client, scraper):
        """
        Args:
            erpnext_client: ERPNext client instance
            shopify_client: Shopify client instance
            scraper: Product scraper instance
        """
        self.erpnext = erpnext_client
        self.shopify = shopify_client
        self.scraper = scraper
        logger.info("Pricing service initialized")

    def scrape_competitor_price(self, item_code: str, competitor_url: str) -> Optional[float]:
        """
        Scrape price from a competitor product page.

        Extraction priority: Shopify .json endpoint, then JSON-LD offers.
        """
        if not competitor_url:
            return None

        # 1. Shopify .json endpoint (all competitors are Shopify stores)
        base = competitor_url.split('?')[0].rstrip('/')
        if '.json' not in base:
            base = f"{base}.json"

        try:
            response = requests.get(
                base,
                headers={'User-Agent': settings.USER_AGENT, 'Accept': 'application/json'},
                timeout=settings.SCRAPE_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            product = data.get('product', data)
            variants = product.get('variants', [])
            if variants and variants[0].get('price'):
                price = float(variants[0]['price'])
                logger.info(f"Scraped price {price} for {item_code} from {base}")
                return price
            logger.warning(f"No variant price in JSON for {item_code}: {base}")
        except Exception as e:
            logger.warning(f"JSON price fetch failed for {item_code} ({base}): {e}")

        # 2. JSON-LD fallback
        try:
            response = requests.get(
                competitor_url,
                headers={'User-Agent': settings.USER_AGENT},
                timeout=settings.SCRAPE_TIMEOUT
            )
            response.raise_for_status()
            match = re.search(
                r'"price"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?', response.text
            )
            if match:
                price = float(match.group(1))
                logger.info(f"Scraped price {price} for {item_code} from JSON-LD")
                return price
        except Exception as e:
            logger.warning(f"JSON-LD price fetch failed for {item_code}: {e}")

        logger.error(f"Could not scrape price for {item_code} from {competitor_url}")
        return None

    def update_erpnext_price_list(
        self,
        item_code: str,
        price: float,
        price_list: str,
        currency: str,
        dry_run: bool = False
    ) -> bool:
        """Create or update the ERPNext Item Price record for a competitor price list"""
        return self.erpnext.upsert_item_price(
            item_code=item_code,
            price=price,
            price_list=price_list,
            currency=currency,
            dry_run=dry_run
        )

    def sync_price_to_shopify(
        self,
        item_code: str,
        shopify_product_id: str,
        price: float,
        dry_run: bool = False
    ) -> bool:
        """
        Update Shopify product variant price.

        Args:
            item_code: ERPNext item code (used to find the variant via metafield)
            shopify_product_id: Shopify product ID (gid://shopify/Product/...) or handle
        """
        if dry_run:
            logger.info(f"DRY RUN: Would update Shopify product {shopify_product_id} price to {price}")
            return True

        # Resolve product: by ID or by metafield lookup
        if shopify_product_id and shopify_product_id.startswith('gid://'):
            product_id = shopify_product_id
        else:
            product = self.shopify.products.search_by_metafield(item_code)
            if not product:
                logger.error(f"No Shopify product found for {item_code}")
                return False
            product_id = product['id']

        # Get the first variant
        query = """
        query getFirstVariant($id: ID!) {
            product(id: $id) {
                variants(first: 1) {
                    edges { node { id price } }
                }
            }
        }
        """
        result = self.shopify.graphql.execute(query, {"id": product_id})
        if not result or not result.get('product'):
            logger.error(f"Failed to fetch product {product_id} for {item_code}")
            return False

        edges = result['product'].get('variants', {}).get('edges', [])
        if not edges:
            logger.error(f"Product {product_id} has no variants")
            return False

        variant_id = edges[0]['node']['id']
        current_price = edges[0]['node'].get('price')
        if current_price is not None and float(current_price) == float(price):
            logger.info(f"{item_code} already priced at {price} in Shopify, skipping")
            return True

        mutation = """
        mutation updatePrice($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
            productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                productVariants { id price }
                userErrors { field message }
            }
        }
        """
        variables = {
            "productId": product_id,
            "variants": [{"id": variant_id, "price": str(price)}]
        }

        data = self.shopify.graphql.execute(mutation, variables)
        if not data or 'productVariantsBulkUpdate' not in data:
            logger.error(f"Failed to update price for {item_code}")
            return False

        errors = data['productVariantsBulkUpdate'].get('userErrors', [])
        if errors:
            for err in errors:
                logger.error(f"Price update error for {item_code}: {err.get('message')}")
            return False

        logger.info(f"Updated Shopify price for {item_code} to {price}")
        return True

    def scrape_and_update_prices(self, limit: Optional[int] = None, dry_run: bool = False) -> Dict[str, int]:
        """
        Scrape competitor prices and update ERPNext price lists for all items.
        Competitor price list + currency come from the competitor config.
        """
        summary = {'updated': 0, 'errors': 0, 'skipped': 0}
        competitors = settings.get_competitors()

        items = list(self.erpnext.get_all_items())
        if limit:
            items = items[:limit]

        logger.info(f"Scraping competitor prices for {len(items)} items")

        for i, item in enumerate(items, 1):
            if i % 10 == 0:
                logger.info(f"Price scrape progress: {i}/{len(items)}")

            url = item.get_priority_link()
            if not url:
                summary['skipped'] += 1
                continue

            competitor = item.get_competitor_from_url(url)
            if not competitor:
                logger.warning(f"No competitor config matches {url} for {item.item_code}")
                summary['skipped'] += 1
                continue

            price = self.scrape_competitor_price(item.item_code, url)
            if price is None:
                summary['errors'] += 1
                continue

            if self.update_erpnext_price_list(
                item_code=item.item_code,
                price=price,
                price_list=competitor['price_list'],
                currency=competitor['currency'],
                dry_run=dry_run
            ):
                summary['updated'] += 1
            else:
                summary['errors'] += 1

        logger.info(f"Price scraping complete: {summary}")
        return summary

    def sync_all_prices_to_shopify(self, price_list: str, limit: Optional[int] = None,
                                   dry_run: bool = False) -> Dict[str, int]:
        """
        Sync ERPNext price list values to Shopify product variants.
        """
        summary = {'updated': 0, 'errors': 0, 'skipped': 0}

        items = list(self.erpnext.get_all_items())
        if limit:
            items = items[:limit]

        logger.info(f"Syncing prices from '{price_list}' to Shopify for {len(items)} items")

        for i, item in enumerate(items, 1):
            if i % 10 == 0:
                logger.info(f"Price sync progress: {i}/{len(items)}")

            price = self.erpnext.get_item_price(item.item_code, price_list)
            if price is None:
                logger.debug(f"No price in '{price_list}' for {item.item_code}, skipping")
                summary['skipped'] += 1
                continue

            if self.sync_price_to_shopify(
                item_code=item.item_code,
                shopify_product_id=item.shopify_product_id or '',
                price=price,
                dry_run=dry_run
            ):
                summary['updated'] += 1
            else:
                summary['errors'] += 1

        logger.info(f"Shopify price sync complete: {summary}")
        return summary
