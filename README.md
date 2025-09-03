# Shopify Product Uploader

A Python CLI tool that automates product migration from ERPNext to Shopify with AI-powered SEO optimization.

## Features

- 🔄 **Automated Product Migration**: Fetches items from ERPNext and creates products in Shopify
- 🎯 **Smart Competitor Analysis**: Scrapes product data from competitor Shopify stores
- 🤖 **AI SEO Optimization**: Uses ChatGPT API to enhance product descriptions
- 🖼️ **Image Management**: Downloads and uploads product images with primary image preservation
- 💾 **Resumable Processing**: SQLite-based state management for interrupted runs
- ✅ **Interactive Approval**: Review and approve each product before upload
- 🚦 **Rate Limiting**: Respects API limits to prevent throttling

## Installation

### Quick Setup (Recommended)

1. Clone the repository:
```bash
git clone <repository-url>
cd shopify_product_uploader
```

2. Run the setup script:
```bash
chmod +x setup.sh
./setup.sh
```

3. Configure your credentials:
```bash
# Edit .env file with your API keys
nano .env  # or use your preferred editor
```

### Manual Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd shopify_product_uploader
```

2. Create and activate virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. Copy and configure environment variables:
```bash
cp .env.example .env
# Edit .env with your credentials
```

5. Create required directories:
```bash
mkdir -p data/images logs
```

## Configuration

Edit `.env` file with your credentials:

```ini
# ERPNext
ERP_BASE_URL=https://your-erpnext.example.com
ERP_API_KEY=your_api_key
ERP_API_SECRET=your_api_secret

# Shopify
SHOPIFY_STORE=my-shop.myshopify.com
SHOPIFY_ADMIN_TOKEN=shpat_xxxxx
SHOPIFY_API_VERSION=2025-01

# OpenAI / ChatGPT
OPENAI_API_KEY=sk-xxxxx
OPENAI_MODEL=gpt-4o-mini

# Behavior
APPROVAL_MODE=manual  # or "auto"
RATE_LIMIT_RPS=1.5
DRY_RUN=false
```

## Usage

### Using Virtual Environment

#### With Run Script (Recommended)
```bash
# The run script automatically activates venv
./run.sh --help
./run.sh --dry-run --limit 1
```

#### Manual Activation
```bash
# Activate virtual environment
source venv/bin/activate

# Run commands
python main.py --help

# Deactivate when done
deactivate
```

### Basic Usage

Process all items from ERPNext:
```bash
./run.sh  # or: python main.py
```

### Process Single Item

```bash
./run.sh --item-code ITEM001
```

### Dry Run (Test Without Uploading)

```bash
./run.sh --dry-run
```

### Batch Processing with Limit

```bash
./run.sh --limit 10 --batch-size 50
```

### Auto-Approval Mode

```bash
./run.sh --default-price 29.99
# Set APPROVAL_MODE=auto in .env
```

### View Statistics

```bash
./run.sh --stats
```

### Reset Failed Item

```bash
./run.sh --reset-item ITEM001
```

### Clear Image Cache

```bash
./run.sh --clear-cache
```

### Export State Backup

```bash
./run.sh --export-state backup.jsonl
```

## Workflow

1. **Fetch Items**: Retrieves items from ERPNext with competitor links
2. **Priority Selection**: Chooses competitor link based on domain priority
3. **Scrape Data**: Extracts product name, description, and images from competitor
4. **Download Images**: Saves images locally with order preservation
5. **SEO Optimization**: Enhances description using ChatGPT AI
6. **Preview**: Shows product details for review
7. **Approval**: User approves and sets price (manual mode)
8. **Upload**: Creates product in Shopify with images and metafields

## State Management

The tool maintains processing state in SQLite database for:
- Resume interrupted runs
- Skip already processed items
- Track failures for retry
- Generate processing statistics

## Image Handling

- Downloads images to `./data/images/<item_code>/`
- Preserves image order (first image = primary)
- Names files with index prefix (000_, 001_, etc.)
- Uploads to Shopify in correct order

## Error Handling

- Automatic retries with exponential backoff
- Graceful fallbacks for scraping failures
- Detailed error logging
- State persistence for recovery

## Logs

Logs are written to:
- Console (colored output)
- File: `./logs/uploader.log`

## Requirements

- Python 3.11+
- ERPNext with custom fields: `custom_competitor_link_1/2/3`
- Shopify store with Admin API access
- OpenAI API key (ChatGPT)

## License

Internal use only. See CLAUDE.md for detailed specifications.