from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any

_LOCK = threading.Lock()
_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "analytics.db")


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_analytics_db() -> None:
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS f1_analytics (
                  conversation_id TEXT PRIMARY KEY,
                  user_id TEXT,
                  project_id TEXT,
                  dialogue_id TEXT,
                  history_json TEXT NOT NULL DEFAULT '[]',
                  metrics_json TEXT NOT NULL DEFAULT '{}',
                  updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS f3_analytics (
                  conversation_id TEXT PRIMARY KEY,
                  user_id TEXT,
                  project_id TEXT,
                  dialogue_id TEXT,
                  note_text TEXT NOT NULL DEFAULT '',
                  cards_json TEXT NOT NULL DEFAULT '[]',
                  metrics_json TEXT NOT NULL DEFAULT '{}',
                  updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS f2_analytics (
                  conversation_id TEXT PRIMARY KEY,
                  user_id TEXT,
                  project_id TEXT,
                  dialogue_id TEXT,
                  history_json TEXT NOT NULL DEFAULT '[]',
                  metrics_json TEXT NOT NULL DEFAULT '{}',
                  updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS f4_analytics (
                  conversation_id TEXT PRIMARY KEY,
                  user_id TEXT,
                  project_id TEXT,
                  dialogue_id TEXT,
                  report_text TEXT NOT NULL DEFAULT '',
                  metrics_json TEXT NOT NULL DEFAULT '{}',
                  updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS f5_analytics (
                  conversation_id TEXT PRIMARY KEY,
                  user_id TEXT,
                  project_id TEXT,
                  dialogue_id TEXT,
                  ai_review_text TEXT NOT NULL DEFAULT '',
                  final_note_text TEXT NOT NULL DEFAULT '',
                  metrics_json TEXT NOT NULL DEFAULT '{}',
                  updated_at INTEGER NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def upsert_f4_analytics(
    *,
    conversation_id: str,
    user_id: str,
    project_id: str,
    dialogue_id: str,
    report_text: str,
    metrics: dict[str, Any],
    updated_at_ms: int,
) -> None:
    if not conversation_id:
        return
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                """
                INSERT INTO f4_analytics
                  (conversation_id, user_id, project_id, dialogue_id, report_text, metrics_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                  user_id=excluded.user_id,
                  project_id=excluded.project_id,
                  dialogue_id=excluded.dialogue_id,
                  report_text=excluded.report_text,
                  metrics_json=excluded.metrics_json,
                  updated_at=excluded.updated_at
                """,
                (
                    conversation_id,
                    user_id,
                    project_id,
                    dialogue_id,
                    report_text or "",
                    json.dumps(metrics or {}, ensure_ascii=False),
                    int(updated_at_ms),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_f4_analytics(conversation_id: str) -> dict[str, Any] | None:
    if not conversation_id:
        return None
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT conversation_id, user_id, project_id, dialogue_id, report_text, metrics_json, updated_at FROM f4_analytics WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    try:
        metrics = json.loads(row["metrics_json"] or "{}")
    except Exception:
        metrics = {}
    return {
        "conversation_id": row["conversation_id"],
        "user_id": row["user_id"] or "",
        "project_id": row["project_id"] or "",
        "dialogue_id": row["dialogue_id"] or "",
        "report_text": row["report_text"] or "",
        "metrics": metrics if isinstance(metrics, dict) else {},
        "updated_at": int(row["updated_at"] or 0),
    }


def upsert_f5_analytics(
    *,
    conversation_id: str,
    user_id: str,
    project_id: str,
    dialogue_id: str,
    ai_review_text: str,
    final_note_text: str,
    metrics: dict[str, Any],
    updated_at_ms: int,
) -> None:
    if not conversation_id:
        return
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                """
                INSERT INTO f5_analytics
                  (conversation_id, user_id, project_id, dialogue_id, ai_review_text, final_note_text, metrics_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                  user_id=excluded.user_id,
                  project_id=excluded.project_id,
                  dialogue_id=excluded.dialogue_id,
                  ai_review_text=excluded.ai_review_text,
                  final_note_text=excluded.final_note_text,
                  metrics_json=excluded.metrics_json,
                  updated_at=excluded.updated_at
                """,
                (
                    conversation_id,
                    user_id,
                    project_id,
                    dialogue_id,
                    ai_review_text or "",
                    final_note_text or "",
                    json.dumps(metrics or {}, ensure_ascii=False),
                    int(updated_at_ms),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_f5_analytics(conversation_id: str) -> dict[str, Any] | None:
    if not conversation_id:
        return None
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT conversation_id, user_id, project_id, dialogue_id, ai_review_text, final_note_text, metrics_json, updated_at FROM f5_analytics WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    try:
        metrics = json.loads(row["metrics_json"] or "{}")
    except Exception:
        metrics = {}
    return {
        "conversation_id": row["conversation_id"],
        "user_id": row["user_id"] or "",
        "project_id": row["project_id"] or "",
        "dialogue_id": row["dialogue_id"] or "",
        "ai_review_text": row["ai_review_text"] or "",
        "final_note_text": row["final_note_text"] or "",
        "metrics": metrics if isinstance(metrics, dict) else {},
        "updated_at": int(row["updated_at"] or 0),
    }


def upsert_f1_analytics(
    *,
    conversation_id: str,
    user_id: str,
    project_id: str,
    dialogue_id: str,
    history: list[dict[str, Any]],
    metrics: dict[str, Any],
    updated_at_ms: int,
) -> None:
    if not conversation_id:
        return
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                """
                INSERT INTO f1_analytics
                  (conversation_id, user_id, project_id, dialogue_id, history_json, metrics_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                  user_id=excluded.user_id,
                  project_id=excluded.project_id,
                  dialogue_id=excluded.dialogue_id,
                  history_json=excluded.history_json,
                  metrics_json=excluded.metrics_json,
                  updated_at=excluded.updated_at
                """,
                (
                    conversation_id,
                    user_id,
                    project_id,
                    dialogue_id,
                    json.dumps(history, ensure_ascii=False),
                    json.dumps(metrics, ensure_ascii=False),
                    int(updated_at_ms),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_f1_analytics(conversation_id: str) -> dict[str, Any] | None:
    if not conversation_id:
        return None
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT conversation_id, user_id, project_id, dialogue_id, history_json, metrics_json, updated_at FROM f1_analytics WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    try:
        history = json.loads(row["history_json"] or "[]")
    except Exception:
        history = []
    try:
        metrics = json.loads(row["metrics_json"] or "{}")
    except Exception:
        metrics = {}
    return {
        "conversation_id": row["conversation_id"],
        "user_id": row["user_id"] or "",
        "project_id": row["project_id"] or "",
        "dialogue_id": row["dialogue_id"] or "",
        "history": history if isinstance(history, list) else [],
        "metrics": metrics if isinstance(metrics, dict) else {},
        "updated_at": int(row["updated_at"] or 0),
    }


def upsert_f2_analytics(
    *,
    conversation_id: str,
    user_id: str,
    project_id: str,
    dialogue_id: str,
    history: list[dict[str, Any]],
    metrics: dict[str, Any],
    updated_at_ms: int,
) -> None:
    if not conversation_id:
        return
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                """
                INSERT INTO f2_analytics
                  (conversation_id, user_id, project_id, dialogue_id, history_json, metrics_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                  user_id=excluded.user_id,
                  project_id=excluded.project_id,
                  dialogue_id=excluded.dialogue_id,
                  history_json=excluded.history_json,
                  metrics_json=excluded.metrics_json,
                  updated_at=excluded.updated_at
                """,
                (
                    conversation_id,
                    user_id,
                    project_id,
                    dialogue_id,
                    json.dumps(history or [], ensure_ascii=False),
                    json.dumps(metrics or {}, ensure_ascii=False),
                    int(updated_at_ms),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_f2_analytics(conversation_id: str) -> dict[str, Any] | None:
    if not conversation_id:
        return None
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT conversation_id, user_id, project_id, dialogue_id, history_json, metrics_json, updated_at FROM f2_analytics WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    try:
        history = json.loads(row["history_json"] or "[]")
    except Exception:
        history = []
    try:
        metrics = json.loads(row["metrics_json"] or "{}")
    except Exception:
        metrics = {}
    return {
        "conversation_id": row["conversation_id"],
        "user_id": row["user_id"] or "",
        "project_id": row["project_id"] or "",
        "dialogue_id": row["dialogue_id"] or "",
        "history": history if isinstance(history, list) else [],
        "metrics": metrics if isinstance(metrics, dict) else {},
        "updated_at": int(row["updated_at"] or 0),
    }


def upsert_f3_analytics(
    *,
    conversation_id: str,
    user_id: str,
    project_id: str,
    dialogue_id: str,
    note_text: str,
    cards: list[dict[str, Any]],
    metrics: dict[str, Any],
    updated_at_ms: int,
) -> None:
    if not conversation_id:
        return
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                """
                INSERT INTO f3_analytics
                  (conversation_id, user_id, project_id, dialogue_id, note_text, cards_json, metrics_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                  user_id=excluded.user_id,
                  project_id=excluded.project_id,
                  dialogue_id=excluded.dialogue_id,
                  note_text=excluded.note_text,
                  cards_json=excluded.cards_json,
                  metrics_json=excluded.metrics_json,
                  updated_at=excluded.updated_at
                """,
                (
                    conversation_id,
                    user_id,
                    project_id,
                    dialogue_id,
                    note_text or "",
                    json.dumps(cards, ensure_ascii=False),
                    json.dumps(metrics, ensure_ascii=False),
                    int(updated_at_ms),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_f3_analytics(conversation_id: str) -> dict[str, Any] | None:
    if not conversation_id:
        return None
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT conversation_id, user_id, project_id, dialogue_id, note_text, cards_json, metrics_json, updated_at FROM f3_analytics WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    try:
        cards = json.loads(row["cards_json"] or "[]")
    except Exception:
        cards = []
    try:
        metrics = json.loads(row["metrics_json"] or "{}")
    except Exception:
        metrics = {}
    return {
        "conversation_id": row["conversation_id"],
        "user_id": row["user_id"] or "",
        "project_id": row["project_id"] or "",
        "dialogue_id": row["dialogue_id"] or "",
        "note_text": row["note_text"] or "",
        "cards": cards if isinstance(cards, list) else [],
        "metrics": metrics if isinstance(metrics, dict) else {},
        "updated_at": int(row["updated_at"] or 0),
    }

