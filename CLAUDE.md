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
9. Always use the latest Shopify API docs from https://shopify.dev/docs/api/admin-graphql/latest before touching APIs and graphql mutations
> ⚠️ **Ethics/Compliance**: Use reasonable rate limiting. This tool is for internal catalog building.

---

## Architecture
The tool has commands like scrape, process, upload. We will break down the workflow for each.

## Processing Pipeline Architecture

The tool operates as a **stateful processing pipeline** where each command validates pipeline stages and avoids reprocessing completed items.

### Content Status Flow
```
null/empty → "Scraped" → "Processed" → "Approved" → "Synchronized"
```

### Pipeline Stage Validation
- **scrape** command: Only processes items with null/empty `content_status`
- **process** command: Only processes items with `content_status = "Scraped"`
- **upload** command: Only processes items with `content_status = "Approved"`
- Each command skips items already in later pipeline stages to prevent reprocessing

### Scrape Command
**Pipeline Stage**: `null/empty` → `"Scraped"`

1. **Fetch Items** from ERPNext (paginated), filtering out items already scraped
2. Skip items with `content_status` in ["Scraped", "Processed", "Approved", "Synchronized"]
3. For each qualifying item:
   - **Pick competitor link** using domain priority order
   - **Scrape** name, product handle, description, image URLs (Shopify JSON → fallbacks)
   - Don't download images in this step (done during upload)
4. **Mark content status as "Scraped"**

### Process Command
**Pipeline Stage**: `"Scraped"` → `"Processed"` → `"Approved"`

1. **Fetch Items** with `content_status = "Scraped"` from ERPNext (paginated)
2. For each item:
   - Call **OpenAI** to **SEO-optimize** the description into Shopify-ready HTML
   - If `custom_shopify_product_handle` field is empty, populate with scraped handle
   - If `custom_shopify_product_name` field is empty, populate with scraped product name
   - Create meta SEO Product title using `custom_product_type`, `custom_brand_custom`, `custom_gender`
   - Create meta SEO Product description following standard SEO practices
   - **Show preview** to user (Product name, SEO title, meta description, description preview)
   - **Ask for user approval** (y/n/q)
3. **Mark content status**:
   - `"Approved"` if user approves
   - `"Processed"` if user wants to review later

### Upload Command
**Pipeline Stage**: `"Approved"` → `"Synchronized"`

1. **Fetch Items** with `content_status = "Approved"` from ERPNext (paginated)
2. For each item:
   - **Preview** to user: show product handle, title, description, image filenames
   - Ask for **approval** + **price** before any changes are made
   - Check if product exists in Shopify by `custom_shopify_product_handle`
   - **Download** images from `custom_scraped_images` field to local cache
   - Create/Update product in Shopify with all metadata
   - Store Shopify product ID in `custom_shopify_product_id` field
3. **Mark content status as "Synchronized"** (final pipeline state)

### Resume and State Management
- Each command checks content status before processing
- Items in later pipeline stages are automatically skipped
- Pipeline can be resumed at any stage without reprocessing completed items
- Status command shows counts for each pipeline stage

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