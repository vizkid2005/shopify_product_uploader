import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

class ProcessStatus(Enum):
    """Product processing status"""
    PENDING = "pending"
    SCRAPED = "scraped"
    IMAGES_DOWNLOADED = "images_downloaded"
    OPTIMIZED = "optimized"
    APPROVED = "approved"
    UPLOADED = "uploaded"
    SKIPPED = "skipped"
    FAILED = "failed"

class StateManager:
    """Manage processing state for resumability"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        logger.info(f"State database initialized at: {self.db_path}")
    
    def _init_database(self):
        """Initialize the SQLite database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create main processing table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS product_state (
                    item_code TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    competitor_url TEXT,
                    product_name TEXT,
                    description TEXT,
                    optimized_description TEXT,
                    image_urls TEXT,
                    image_paths TEXT,
                    shopify_product_id TEXT,
                    price TEXT,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create processing log table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processing_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_code TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (item_code) REFERENCES product_state(item_code)
                )
            """)
            
            # Create index for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status 
                ON product_state(status)
            """)
            
            conn.commit()
    
    def get_product_state(self, item_code: str) -> Optional[Dict[str, Any]]:
        """Get the current state of a product"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM product_state WHERE item_code = ?
            """, (item_code,))
            
            row = cursor.fetchone()
            if row:
                state = dict(row)
                # Deserialize JSON fields
                for field in ['image_urls', 'image_paths']:
                    if state.get(field):
                        state[field] = json.loads(state[field])
                return state
            
            return None
    
    def update_product_state(self, 
                           item_code: str,
                           status: ProcessStatus,
                           **kwargs) -> None:
        """Update or create product state"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Serialize list fields
            for field in ['image_urls', 'image_paths']:
                if field in kwargs and kwargs[field] is not None:
                    kwargs[field] = json.dumps(kwargs[field])
            
            # Check if record exists
            existing = self.get_product_state(item_code)
            
            if existing:
                # Update existing record
                fields = []
                values = []
                for key, value in kwargs.items():
                    fields.append(f"{key} = ?")
                    values.append(value)
                
                fields.append("status = ?")
                values.append(status.value)
                fields.append("updated_at = CURRENT_TIMESTAMP")
                values.append(item_code)
                
                query = f"""
                    UPDATE product_state 
                    SET {', '.join(fields)}
                    WHERE item_code = ?
                """
                cursor.execute(query, values)
                
            else:
                # Insert new record
                kwargs['item_code'] = item_code
                kwargs['status'] = status.value
                
                fields = list(kwargs.keys())
                placeholders = ['?' for _ in fields]
                values = [kwargs[f] for f in fields]
                
                query = f"""
                    INSERT INTO product_state ({', '.join(fields)})
                    VALUES ({', '.join(placeholders)})
                """
                cursor.execute(query, values)
            
            conn.commit()
            logger.debug(f"Updated state for {item_code}: {status.value}")
    
    def log_action(self, item_code: str, action: str, details: Optional[str] = None):
        """Log a processing action"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO processing_log (item_code, action, details)
                VALUES (?, ?, ?)
            """, (item_code, action, details))
            conn.commit()
    
    def get_pending_items(self) -> List[str]:
        """Get list of items that haven't been fully processed"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT item_code FROM product_state
                WHERE status NOT IN (?, ?, ?)
                ORDER BY created_at
            """, (ProcessStatus.UPLOADED.value, 
                  ProcessStatus.SKIPPED.value,
                  ProcessStatus.FAILED.value))
            
            return [row[0] for row in cursor.fetchall()]
    
    def get_statistics(self) -> Dict[str, int]:
        """Get processing statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM product_state
                GROUP BY status
            """)
            
            stats = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Add total
            stats['total'] = sum(stats.values())
            
            return stats
    
    def mark_failed(self, item_code: str, error_message: str):
        """Mark an item as failed with error message"""
        self.update_product_state(
            item_code,
            ProcessStatus.FAILED,
            error_message=error_message
        )
        self.log_action(item_code, "FAILED", error_message)
        logger.error(f"Marked {item_code} as failed: {error_message}")
    
    def reset_item(self, item_code: str):
        """Reset an item to pending status"""
        self.update_product_state(item_code, ProcessStatus.PENDING)
        self.log_action(item_code, "RESET", "Item reset to pending")
        logger.info(f"Reset {item_code} to pending")
    
    def clear_all_data(self):
        """Clear all data (use with caution)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM processing_log")
            cursor.execute("DELETE FROM product_state")
            conn.commit()
        logger.warning("Cleared all state data")
    
    def export_to_jsonl(self, output_path: Path):
        """Export state to JSONL for backup"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM product_state")
            
            with open(output_path, 'w') as f:
                for row in cursor.fetchall():
                    record = dict(row)
                    # Deserialize JSON fields
                    for field in ['image_urls', 'image_paths']:
                        if record.get(field):
                            record[field] = json.loads(record[field])
                    f.write(json.dumps(record) + '\n')
        
        logger.info(f"Exported state to {output_path}")