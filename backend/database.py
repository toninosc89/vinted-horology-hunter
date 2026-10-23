from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from backend.schemas import LLMRouterSettings, WatchAppraisal

load_dotenv()

DB_PATH = Path(__file__).resolve().parent / "horology_hunter.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target = db_path or DB_PATH
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS appraisal_cache (
                    vinted_id INTEGER NOT NULL,
                    price_listed_eur REAL NOT NULL,
                    appraisal_json TEXT NOT NULL,
                    description_text TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (vinted_id, price_listed_eur)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS router_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    settings_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
    finally:
        conn.close()


def get_cached_appraisal(
    vinted_id: int,
    price_listed_eur: Optional[float] = None,
    db_path: Optional[Path] = None,
) -> Optional[WatchAppraisal]:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if price_listed_eur is not None:
            row = conn.execute(
                """
                SELECT appraisal_json FROM appraisal_cache
                WHERE vinted_id = ? AND ABS(price_listed_eur - ?) < 0.01
                """,
                (vinted_id, float(price_listed_eur)),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT appraisal_json FROM appraisal_cache
                WHERE vinted_id = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (vinted_id,),
            ).fetchone()

        if not row:
            return None
        data = json.loads(row["appraisal_json"])
        appraisal = WatchAppraisal.model_validate(data)
        return appraisal
    except Exception:
        return None
    finally:
        conn.close()


def get_cached_description(
    vinted_id: int, db_path: Optional[Path] = None
) -> str:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT description_text FROM appraisal_cache
            WHERE vinted_id = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (vinted_id,),
        ).fetchone()
        return row["description_text"] if row and row["description_text"] else ""
    finally:
        conn.close()


def save_cached_appraisal(
    appraisal: WatchAppraisal,
    description_text: str = "",
    db_path: Optional[Path] = None,
) -> None:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO appraisal_cache (vinted_id, price_listed_eur, appraisal_json, description_text, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(vinted_id, price_listed_eur) DO UPDATE SET
                    appraisal_json = excluded.appraisal_json,
                    description_text = CASE WHEN excluded.description_text != '' THEN excluded.description_text ELSE appraisal_cache.description_text END,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    appraisal.vinted_id,
                    float(appraisal.price_listed_eur),
                    appraisal.model_dump_json(),
                    description_text,
                ),
            )
    finally:
        conn.close()


def clear_appraisal_cache(db_path: Optional[Path] = None) -> int:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute("DELETE FROM appraisal_cache")
            return cursor.rowcount
    finally:
        conn.close()


def load_router_settings(db_path: Optional[Path] = None) -> LLMRouterSettings:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT settings_json FROM router_settings WHERE id = 1"
        ).fetchone()
        if row:
            saved = LLMRouterSettings.model_validate(json.loads(row["settings_json"]))
        else:
            saved = LLMRouterSettings()

        # Merge with environment variables if UI values are empty
        if not saved.gemini_api_key and os.getenv("GEMINI_API_KEY"):
            saved.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        if not saved.openai_api_key and os.getenv("OPENAI_API_KEY"):
            saved.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        if not saved.anthropic_api_key and os.getenv("ANTHROPIC_API_KEY"):
            saved.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not saved.groq_api_key and os.getenv("GROQ_API_KEY"):
            saved.groq_api_key = os.getenv("GROQ_API_KEY", "")
        if not saved.deepseek_api_key and os.getenv("DEEPSEEK_API_KEY"):
            saved.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not saved.openrouter_api_key and os.getenv("OPENROUTER_API_KEY"):
            saved.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        if os.getenv("OLLAMA_BASE_URL"):
            saved.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        return saved
    finally:
        conn.close()


def save_router_settings(
    settings: LLMRouterSettings, db_path: Optional[Path] = None
) -> LLMRouterSettings:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO router_settings (id, settings_json, updated_at)
                VALUES (1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    settings_json = excluded.settings_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (settings.model_dump_json(),),
            )
        return settings
    finally:
        conn.close()
