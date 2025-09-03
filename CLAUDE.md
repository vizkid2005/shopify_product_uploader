## Goal
Write a **Python 3.11** CLI tool that:
1. Iterates over all **ERPNext Items** and reads custom fields: `custom_competitor_link_1`, `custom_competitor_link_2`, `custom_competitor_link_3`.
2. Chooses ONE competitor link per item according to **priority order**:
   1) `ourascents.com` → 2) `hamidi.ae` → 3) `hamidi.us` (highest to lowest). Use the highest-priority **non-empty** link that matches the domain.
3. Scrapes that product page to extract: **product name**, **description**, **all product images**.
   - Prefer Shopify’s `*.json` endpoint for structured product data (append `.json` to the product URL when possible).
   - If the JSON endpoint is blocked/unavailable, gracefully fall back to **JSON-LD**, then **Open Graph tags**, then a conservative HTML parse (gallery selectors).
   - Download image files locally (no hotlinking) and prepare them for upload.
4. **SEO-optimize the description** via the **Anthropic Claude Messages API** (configurable model), returning **Shopify-ready HTML**.
5. Create a **new Shopify product** using:
   - `handle = ERPNext Item Code` (to maintain 1:1 mapping)
   - `metafield (namespace: "erpnext", key: "item_code") = ERPNext Item Code`
   - `title = scraped name`
   - `description_html = SEO-optimized HTML from Claude`
   - Images = the **downloaded** files (uploaded to Shopify)
   - Create **one default variant** with **price** provided **interactively** by the user.
6. **Skip** creation if a Shopify product already exists for the ERPNext Item (check by **handle** OR metafield).
7. **Per item**, before uploading, show a **preview** (ERPNext Item Code, proposed Title, SEO Description summary, image file names) and prompt the user for:
   - **Approval (y/N)** to upload
   - **Price** (required to proceed)
   - Optional: edit the description in $EDITOR before upload
8. Provide robust logging, resumability, and rate limiting.

> ⚠️ **Ethics/Compliance**: Use reasonable rate limiting. This tool is for internal catalog building.

---

## High-Level Flow
1. **Fetch Items** from ERPNext (paginated).
2. For each Item, **pick competitor link** using the domain priority order.
3. **Scrape** name, description, image URLs (Shopify JSON if possible → otherwise fallbacks).
4. **Download** images to a local cache folder (e.g., `./data/images/<item_code>/...`).
5. Call **Claude** to **SEO-optimize** the description into Shopify-ready HTML.
6. **Preview** to user: show product id (ERPNext item_code), title, first 300 chars of description, image filenames; ask for **approval** + **price**.
7. **Check existence** in Shopify via **GraphQL** product search (by handle==item_code OR metafield).
8. If approved and not existing: **create product** (REST or GraphQL) with handle=item_code, description_html, images (upload actual files), variant (price, sku=item_code).
9. **Persist progress** (SQLite or JSONL) so the tool can resume and so items aren’t reprocessed unnecessarily.
10. Move on to next item.

---

## Technical Choices
- **Language**: Python 3.11
- **HTTP**: `requests`
- **Parsing**: `beautifulsoup4` + `lxml`
- **Retries**: `tenacity`
- **CLI UX**: `argparse`, optional `$EDITOR` support
- **SEO**: `anthropic` SDK (Claude Messages API)
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

# Anthropic / Claude
ANTHROPIC_API_KEY=sk-ant-xxx
CLAUDE_MODEL=claude-3-7-sonnet-2025-08

# Behavior
IMAGE_DIR=./data/images
PAGE_SIZE=100
RATE_LIMIT_RPS=1.5
DRY_RUN=false
APPROVAL_MODE=manual   # manual|auto
LOG_LEVEL=INFO