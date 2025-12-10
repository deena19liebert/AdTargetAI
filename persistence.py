# app/persistence.py
from pathlib import Path
import sqlite3
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = EXPORT_DIR / "campaigns.db"

def init_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS campaigns (
        campaign_id TEXT PRIMARY KEY,
        created_at TEXT,
        data TEXT
    )
    """)
    conn.commit()
    return conn

_db_conn = init_db()

def save_campaign_to_db(campaign_id: str, data: Dict[str, Any]) -> None:
    try:
        cur = _db_conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO campaigns (campaign_id, created_at, data) VALUES (?, ?, ?)",
            (campaign_id, datetime.utcnow().isoformat(), json.dumps(data, default=str, ensure_ascii=False))
        )
        _db_conn.commit()
        file_path = EXPORT_DIR / f"{campaign_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.info("Saved campaign %s to DB and file %s", campaign_id, file_path)
    except Exception:
        logger.exception("Failed to persist campaign %s", campaign_id)

def load_campaign(campaign_id: str) -> Optional[Dict[str, Any]]:
    try:
        cur = _db_conn.cursor()
        cur.execute("SELECT data FROM campaigns WHERE campaign_id = ?", (campaign_id,))
        row = cur.fetchone()
        if row:
            return json.loads(row[0])
    except Exception:
        logger.exception("DB load error for %s", campaign_id)

    try:
        file_path = EXPORT_DIR / f"{campaign_id}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        logger.exception("File fallback load error for %s", campaign_id)

    return None

def list_campaigns() -> List[str]:
    try:
        cur = _db_conn.cursor()
        cur.execute("SELECT campaign_id FROM campaigns ORDER BY created_at DESC")
        return [r[0] for r in cur.fetchall()]
    except Exception:
        logger.exception("Failed to list campaigns from DB")
        try:
            return [p.stem for p in EXPORT_DIR.glob("campaign_*.json")]
        except Exception:
            return []
