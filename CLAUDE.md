# Shopify Product Uploader

## Goal

Build a modular **Python 3.11 CLI tool suite** for managing product data across **ERPNext**, **Shopify**, and **multiple competitor websites**. The system handles scraping, SEO optimization, pricing synchronization, stock updates, and Shopify publishing—using a **configurable competitor registry** and two **parallel lifecycle statuses**.

## Core Requirements

### 1. Competitor Configuration (Fully Dynamic)

Instead of fixed competitor fields, provide a **configurable competitor list** in a JSON/YAML file, database table, or Python config object. Each competitor entry contains:

- `competitor_name` — display/identifier name
- `domain` — top-level domain (no `www`), matched against the competitor link fields
- `price_list` — the ERPNext Price List name used to store scraped prices
- `currency` — `CAD` or `USD`

Example:

```json
[
  {
    "competitor_name": "Ariaz",
    "domain": "ariaz.ca",
    "price_list": "Ariaz Online",
    "currency": "CAD"
  },
  {
    "competitor_name": "Ourascents",
    "domain": "ourascents.com",
    "price_list": "Ourascents Online",
    "currency": "USD"
  }
]
```

#### Competitor Links in ERPNext

ERPNext Item contains three custom link fields:

- `custom_competitor_link_1`
- `custom_competitor_link_2`
- `custom_competitor_link_3`

Each product must have **at least one** competitor link to be processed.

#### Product Exclusion

ERPNext Item contains a checkbox field:

- `custom_exclude_from_online_stores`

When this field is checked (set to `1`), the product is **completely excluded** from all pipeline stages:

- **Scraping** - product is skipped
- **Processing** - product is skipped
- **Upload** - product is skipped
- **Stock sync** - product is skipped (not in Shopify)
- **Pricing** - product is skipped

Products with this flag enabled are treated as if they **do not exist** in the system. This allows ERPNext to maintain items that should never be published to online stores.

#### Domain Matching

The scraper determines which competitor link to use by:

1. Checking all competitor link fields
2. Matching each URL's domain to a **competitor.domain**
3. Selecting the match with the **highest priority** from the configured competitor list

Priority is defined by the order in the competitor config (index 0 = highest priority).

### 2. Scraping Rules

For each item, the scraping tool must:

- Identify the correct competitor based on domain + priority
- Scrape product:
  - **Name**
  - **Shopify handle**
  - **Description**
  - **All image URLs**
- Extraction priority:
  1. Shopify `.json` endpoint
  2. JSON-LD
  3. Open Graph tags
  4. Manual HTML selectors

Ariaz's description must remain **exactly as-is (no SEO rewrite)**. All other competitors get **SEO-optimized** descriptions during processing.

### 3. Pricing Tools

Create a suite of pricing tools:

#### 3.1 Fetch & Store Competitor Prices

- Fetch latest price from competitor product page
- Update the competitor's ERPNext Price List (configurable)
- Store price in correct currency

#### 3.2 Update Online Store Pricing

- Sync ERPNext price list → Shopify product price
- Used for each online store (multiple shops supported)

### 4. Stock Sync Tool

A `stock-sync` command updates Shopify inventory based on ERPNext stock levels:

- If ERPNext stock `< 2`:
  - Set Shopify stock = 0
  - Mark variant as **Sold Out**
- Otherwise:
  - Update Shopify with the actual ERPNext quantity

This keeps storefront inventory truthful and prevents overselling.

## Dual Lifecycle System

Each product follows **two independent lifecycles**.

### Content Lifecycle (ERPNext Item Field – Configurable)

Field name should be configurable (e.g., `custom_content_status`)

Possible values:

#### `SCRAPED`

- Metadata extracted from highest-priority competitor
- Ready for SEO processing

#### `OPTIMIZED`

- Description SEO-optimized and updated
- Shopify upload is now **pending**

#### `APPROVED`

- Human-reviewed, ready for final Shopify upload

#### `OVERRIDE`

- Shopify content was manually edited
- **Do NOT overwrite on future uploads**

### Shopify Upload Status (ERPNext Field – Configurable)

Possible values:

#### `PENDING`

- Content is APPROVED but not yet uploaded

#### `SYNCED`

- Shopify content is fully updated

#### `SKIPPED`

- Item is in OVERRIDE state → skip uploads

## Pipeline Architecture

The CLI has modular commands:

```
scrape → process → pricing → stock-sync → upload
```

Each module checks the correct lifecycle fields and skips items in later stages.

## Commands

### Scrape Command

**State:** `null/empty → SCRAPED`

**Steps:**

1. Fetch ERPNext items where **content status is empty**
2. For each item:
   - Match competitor based on link + domain
   - Scrape metadata
   - Save scraped fields to ERPNext
3. Set content status → **SCRAPED**
4. No images downloaded yet (done during upload)

### Process Command

**State:** `SCRAPED → OPTIMIZED → APPROVED`

**Steps:**

1. Fetch items with `SCRAPED`
2. If competitor is Ariaz → keep description unchanged
3. Otherwise:
   - Use OpenAI to generate:
     - SEO-optimized Shopify HTML description
     - SEO meta title
     - SEO meta description
4. Show preview → user approves or defers
5. Status transitions:
   - Approved → `APPROVED`
   - Deferred → `OPTIMIZED`

### Pricing Command

Two subcommands:

#### `pricing scrape-prices`

- Fetch competitor page price
- Write to configured competitor price list in ERPNext

#### `pricing update-shopify`

- Push ERPNext price list values to Shopify
- Supports multiple stores

### Stock Sync Command

Command: `stock-sync`

- Pull ERPNext stock value
- If `< 2`:
  - Push stock = 0 to Shopify
  - Mark variant as sold out
- Else:
  - Push actual quantity
- Log all changes

### Upload Command

**State:** `APPROVED → SYNCED`

**Steps:**

1. Fetch items with `APPROVED`
2. Preview: title, handle, images
3. Request final approval
4. Download images
5. Create/Update Shopify product using REST Admin API
6. Set upload status → **SYNCED**
7. Set content status → remains `APPROVED` unless override occurs

## Technical Stack

- Python 3.11
- `requests`
- `beautifulsoup4`, `lxml`
- `tenacity`
- `openai`
- Shopify Admin GraphQL (search)
- Shopify REST (product + image upload)
- SQLite state tracking + JSONL logs
- `python-dotenv`

## Environment Variables

```ini
# ERPNext
ERP_BASE_URL=
ERP_API_KEY=
ERP_API_SECRET=

# Shopify
SHOPIFY_STORE=
SHOPIFY_ADMIN_TOKEN=
SHOPIFY_API_VERSION=2025-01

# OpenAI
OPENAI_API_KEY=

# Competitor Config File
COMPETITOR_CONFIG=./competitors.json

# Behavior
IMAGE_DIR=./data/images
PAGE_SIZE=100
RATE_LIMIT_RPS=1.5
DRY_RUN=false
LOG_LEVEL=INFO
```
