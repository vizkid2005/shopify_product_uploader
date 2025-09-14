## Goal
Write a **Python 3.11** CLI tool that:
1. Iterates over all **ERPNext Items** and reads custom fields: `custom_competitor_link_1`, `custom_competitor_link_2`, `custom_competitor_link_3`.
2. Chooses ONE competitor link per item according to **priority order**:
   1) `ourascents.com` → 2) `hamidi.ae` → 3) `hamidi.us` (highest to lowest). Use the highest-priority **non-empty** link that matches the domain.
3. Scrapes that product page to extract: **product name**, **shopify handle** **description**, **all product images**.
   - Prefer Shopify’s `*.json` endpoint for structured product data (append `.json` to the product URL when possible).
   - If the JSON endpoint is blocked/unavailable, gracefully fall back to **JSON-LD**, then **Open Graph tags**, then a conservative HTML parse (gallery selectors).
   - Download image files locally (no hotlinking) and prepare them for upload.
4. **SEO-optimize the description meta title and description ** via OpenAI API** (configurable model), returning **Shopify-ready HTM and titleL**.
5. Create a **new Shopify product** using:
   - `handle = custom_shopify_product_handle field in ERPNext Item` (to maintain 1:1 mapping)
   - `metafield (namespace: "erpnext", key: "item_code") = ERPNext Item Code`
   - `title = scraped name`
   - `description_html = SEO-optimized HTML from OpenAI`
   - Images = the **downloaded** files (uploaded to Shopify)
   - Create **one default variant** with **price** provided **interactively** by the user.
6. **Skip** creation if a Shopify product already exists for the ERPNext Item (check by custom_shopify_product_handle).
7. **Per item**, before uploading, show a **preview** (Product Handle, proposed Title, SEO Description summary, image file names) and prompt the user for:
   - **Approval (y/N)** to upload
   - **Price** (required to proceed)
   - Optional: edit the description in $EDITOR before upload
8. Provide robust logging, resumability, and rate limiting.
9. Use the latest Shopify API docs from https://shopify.dev/docs/api/admin-graphql/latest for reference and creating the right queries
> ⚠️ **Ethics/Compliance**: Use reasonable rate limiting. This tool is for internal catalog building.

---

## Architecture
The tool has commands like scrape, process, upload. We will break down the workflow for each.

Overall flow is Scraped -> Processed -> Uploaded. 

For every command we will  **Persist progress** (SQLite or JSONL) so the tool can resume and so items aren’t reprocessed unnecessarily through every stage of the pipeline.

### Scrape command
1. **Fetch Items** from ERPNext (paginated).
2. For each Item, **pick competitor link** using the domain priority order.
3. **Scrape** name, product handle, description, image URLs (Shopify JSON if possible → otherwise fallbacks). Don't download images in this step
4. Mark content status as Scraped

### Process command
1. **Fetch Items** from ERPNext (paginated).

For each item
1. Call **OpenAI** to **SEO-optimize** the description into Shopify-ready HTML.
2. If custom_shopify_product_handle field is empty, populate it with the scraped handle, else leave as is
3. if custom_shopify_product_name field is empty, populate it with the scraped product name
4. Create a meta SEO Product title that is short and store it in custom_shopify_seo_title field. Use the custom_product_type, custom_brand_custom and custom_gender separated by | if possible. Call **OpenAI** to check if this makes sense or ask for a fallback from **OpenAI**
5. Create a meta SEO Product description that is inline with standard SEO practices and store it in custom_shopify_meta_description field
6. Mark content as Processed

### Upload
1. **Fetch Items** from ERPNext (paginated).

For each item
0. **Preview** to user: show product handle, title, description, image filenames; ask for **approval** + **price** before any changes are made in Shopify and ERPNext. 
1. Check if product exists in Shopify by checking if custom_shopify_product_handle exists 
2. If the product exists, we need to compare if data in ERPNext is different than that in Shopify. ERPNext is the source of truth and will override whatever is in shopify. Update product name, description, images. Images should be taken from custom_scraped_images field.
3. **Download** images given in custom_scraped_images field to a local cache folder (e.g., `./data/images/<item_code>/...`).
4. If product does not exist, then create a new product using the product with handle custom_shopify_product_handle and item name from custom_shopify_product_name, description from custom_shopify_description_html, images downloaded in step 3 maintaining order
5. Get the Shopify product id of the product and add it to custom_shopify_product_id field in ERPNext.
6. Mark content status as Uploaded

---

## Technical Choices
- **Language**: Python 3.11
- **HTTP**: `requests`
- **Parsing**: `beautifulsoup4` + `lxml`
- **Retries**: `tenacity`
- **CLI UX**: `argparse`, optional `$EDITOR` support
- **SEO**: `openai` SDK (OpenAi Messages API)
- **Shopify**: 
  - **GraphQL** Admin API for **search/existence check**
  - **REST** Admin API for **product creation + image upload with base64 “attachment”** (simpler than GraphQL staged uploads)
- **State**: SQLite DB (`sqlite3`) to track per-item status + a simple JSONL log
- **Env management**: `python-dotenv`

---

## Environment Variables (`.env`)
Create a `.env` file (do not commit real secrets):
```ini
# ERPNext
ERP_BASE_URL=https://your-erpnext.example.com
ERP_API_KEY=xxxx
ERP_API_SECRET=yyyy

# Shopify
SHOPIFY_STORE=my-shop.myshopify.com
SHOPIFY_ADMIN_TOKEN=shpat_xxx
SHOPIFY_API_VERSION=2025-01

# OpenAI / ChatGPT Configuration
OPENAI_API_KEY=

# Behavior
IMAGE_DIR=./data/images
PAGE_SIZE=100
RATE_LIMIT_RPS=1.5
DRY_RUN=false
APPROVAL_MODE=manual   # manual|auto
LOG_LEVEL=INFO