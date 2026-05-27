import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from .settings_manager import SettingsManager
except ImportError:
    # Fallback for direct execution or different import context
    import sys
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from core.settings_manager import SettingsManager

AUDIT_DB_PATH = Path(__file__).resolve().parents[2] / "audit.db"

class AuditLogger:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AuditLogger, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._init_db()
        self._initialized = True

    def _init_db(self):
        """Initialize the audit database."""
        conn = sqlite3.connect(AUDIT_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                job_id TEXT,
                model TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost REAL,
                endpoint TEXT
            )
        """)
        conn.commit()
        conn.close()

    def log_usage(self, 
                  model: str, 
                  usage: Dict[str, Any], 
                  job_id: Optional[str] = None, 
                  endpoint: str = "chat.completions"):
        """
        Log API usage to the database.
        usage dict expected keys: prompt_tokens, completion_tokens, total_tokens
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        
        # Simple cost estimation (standardize on approx rates if unknown, e.g. gemini-3-pro-preview)
        # These are rough estimates for general calculation, can be refined.
        # Rates per 1M tokens
        cost = 0.0
        
        # Calculate cost using dynamic settings
        settings_manager = SettingsManager()
        cost_config = settings_manager.get_model_cost_config(model)
        
        input_price = cost_config.get("input_price", 0.0)
        output_price = cost_config.get("output_price", 0.0)
        
        cost = (prompt_tokens / 1_000_000 * input_price) + (completion_tokens / 1_000_000 * output_price)

        try:
            conn = sqlite3.connect(AUDIT_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_usage (timestamp, job_id, model, prompt_tokens, completion_tokens, total_tokens, cost, endpoint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (time.time(), job_id, model, prompt_tokens, completion_tokens, total_tokens, cost, endpoint))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[AuditLogger] Error logging usage: {e}")

    def get_logs(self, limit: int = 100, offset: int = 0):
        """Retrieve logs from the database."""
        conn = sqlite3.connect(AUDIT_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM api_usage ORDER BY timestamp DESC LIMIT ? OFFSET ?
        """, (limit, offset))
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_stats(self):
        """Get aggregated statistics."""
        conn = sqlite3.connect(AUDIT_DB_PATH)
        cursor = conn.cursor()
        
        stats = {}
        
        # Total cost
        cursor.execute("SELECT SUM(cost), SUM(total_tokens) FROM api_usage")
        res = cursor.fetchone()
        stats["total_cost"] = res[0] or 0.0
        stats["total_tokens"] = res[1] or 0

        # Cost per job (top 10)
        cursor.execute("""
            SELECT job_id, SUM(cost) as job_cost, SUM(total_tokens) as job_tokens 
            FROM api_usage 
            WHERE job_id IS NOT NULL 
            GROUP BY job_id 
            ORDER BY job_cost DESC 
            LIMIT 10
        """)
        stats["top_jobs"] = [{"job_id": row[0], "cost": row[1], "tokens": row[2]} for row in cursor.fetchall()]

        conn.close()
        return stats
