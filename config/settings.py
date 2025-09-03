import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # ERPNext
    ERP_BASE_URL: str = os.getenv("ERP_BASE_URL", "")
    ERP_API_KEY: str = os.getenv("ERP_API_KEY", "")
    ERP_API_SECRET: str = os.getenv("ERP_API_SECRET", "")
    
    # Shopify
    SHOPIFY_STORE: str = os.getenv("SHOPIFY_STORE", "")
    SHOPIFY_ADMIN_TOKEN: str = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
    SHOPIFY_API_VERSION: str = os.getenv("SHOPIFY_API_VERSION", "2025-01")
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # Paths
    IMAGE_DIR: Path = Path(os.getenv("IMAGE_DIR", "./data/images"))
    DB_PATH: Path = Path(os.getenv("DB_PATH", "./data/state.db"))
    LOG_FILE: Path = Path(os.getenv("LOG_FILE", "./logs/uploader.log"))
    
    # Behavior
    PAGE_SIZE: int = int(os.getenv("PAGE_SIZE", "100"))
    RATE_LIMIT_RPS: float = float(os.getenv("RATE_LIMIT_RPS", "1.5"))
    DRY_RUN: bool = os.getenv("DRY_RUN", "false").lower() == "true"
    APPROVAL_MODE: str = os.getenv("APPROVAL_MODE", "manual")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Scraping
    USER_AGENT: str = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; ProductUploader/1.0)")
    SCRAPE_TIMEOUT: int = int(os.getenv("SCRAPE_TIMEOUT", "30"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    
    # Competitor priority order
    COMPETITOR_PRIORITY = [
        "ourascents.com",
        "hamidi.ae", 
        "hamidi.us"
    ]
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required settings are present"""
        required = [
            cls.ERP_BASE_URL,
            cls.ERP_API_KEY,
            cls.ERP_API_SECRET,
            cls.SHOPIFY_STORE,
            cls.SHOPIFY_ADMIN_TOKEN,
            cls.OPENAI_API_KEY
        ]
        
        missing = [name for name, value in zip(
            ["ERP_BASE_URL", "ERP_API_KEY", "ERP_API_SECRET", 
             "SHOPIFY_STORE", "SHOPIFY_ADMIN_TOKEN", "OPENAI_API_KEY"],
            required
        ) if not value]
        
        if missing:
            raise ValueError(f"Missing required settings: {', '.join(missing)}")
        
        # Create directories if they don't exist
        cls.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        cls.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        cls.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        return True
    
    @classmethod
    def get_shopify_api_url(cls, endpoint: str = "") -> str:
        """Get Shopify API URL"""
        return f"https://{cls.SHOPIFY_STORE}/admin/api/{cls.SHOPIFY_API_VERSION}/{endpoint}"
    
    @classmethod
    def get_shopify_graphql_url(cls) -> str:
        """Get Shopify GraphQL URL"""
        return f"https://{cls.SHOPIFY_STORE}/admin/api/{cls.SHOPIFY_API_VERSION}/graphql.json"

settings = Settings()