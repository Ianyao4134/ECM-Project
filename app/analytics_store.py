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


def list_all_analytics_for_user(user_id: str) -> dict[str, list[dict[str, Any]]]:
    """
    Mentor / owner: all analytics rows for a student (by user_id), safe summaries only (no full history text).
    """
    if not user_id:
        return {"f1": [], "f2": [], "f3": [], "f4": [], "f5": []}
    out: dict[str, list[dict[str, Any]]] = {"f1": [], "f2": [], "f3": [], "f4": [], "f5": []}
    with _LOCK:
        conn = _conn()
        try:
            r1 = conn.execute(
                """
                SELECT conversation_id, project_id, dialogue_id, updated_at, metrics_json,
                       length(history_json) AS history_bytes
                FROM f1_analytics WHERE user_id = ? ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            for r in r1:
                metrics: dict[str, Any] = {}
                try:
                    m = json.loads(r["metrics_json"] or "{}")
                    if isinstance(m, dict):
                        metrics = m
                except Exception:
                    metrics = {}
                out["f1"].append(
                    {
                        "conversation_id": r["conversation_id"],
                        "project_id": r["project_id"] or "",
                        "dialogue_id": r["dialogue_id"] or "",
                        "updated_at": int(r["updated_at"] or 0),
                        "metrics": metrics,
                        "history_payload_bytes": int(r["history_bytes"] or 0),
                    }
                )

            r2 = conn.execute(
                """
                SELECT conversation_id, project_id, dialogue_id, updated_at, metrics_json,
                       length(history_json) AS history_bytes
                FROM f2_analytics WHERE user_id = ? ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            for r in r2:
                metrics = {}
                try:
                    m = json.loads(r["metrics_json"] or "{}")
                    if isinstance(m, dict):
                        metrics = m
                except Exception:
                    metrics = {}
                out["f2"].append(
                    {
                        "conversation_id": r["conversation_id"],
                        "project_id": r["project_id"] or "",
                        "dialogue_id": r["dialogue_id"] or "",
                        "updated_at": int(r["updated_at"] or 0),
                        "metrics": metrics,
                        "history_payload_bytes": int(r["history_bytes"] or 0),
                    }
                )

            r3 = conn.execute(
                """
                SELECT conversation_id, project_id, dialogue_id, updated_at, metrics_json,
                       length(note_text) AS note_len, length(cards_json) AS cards_bytes
                FROM f3_analytics WHERE user_id = ? ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            for r in r3:
                metrics = {}
                try:
                    m = json.loads(r["metrics_json"] or "{}")
                    if isinstance(m, dict):
                        metrics = m
                except Exception:
                    metrics = {}
                out["f3"].append(
                    {
                        "conversation_id": r["conversation_id"],
                        "project_id": r["project_id"] or "",
                        "dialogue_id": r["dialogue_id"] or "",
                        "updated_at": int(r["updated_at"] or 0),
                        "metrics": metrics,
                        "note_char_len": int(r["note_len"] or 0),
                        "cards_payload_bytes": int(r["cards_bytes"] or 0),
                    }
                )

            r4 = conn.execute(
                """
                SELECT conversation_id, project_id, dialogue_id, updated_at, metrics_json,
                       length(report_text) AS report_len
                FROM f4_analytics WHERE user_id = ? ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            for r in r4:
                metrics = {}
                try:
                    m = json.loads(r["metrics_json"] or "{}")
                    if isinstance(m, dict):
                        metrics = m
                except Exception:
                    metrics = {}
                out["f4"].append(
                    {
                        "conversation_id": r["conversation_id"],
                        "project_id": r["project_id"] or "",
                        "dialogue_id": r["dialogue_id"] or "",
                        "updated_at": int(r["updated_at"] or 0),
                        "metrics": metrics,
                        "report_char_len": int(r["report_len"] or 0),
                    }
                )

            r5 = conn.execute(
                """
                SELECT conversation_id, project_id, dialogue_id, updated_at, metrics_json,
                       length(ai_review_text) AS review_len, length(final_note_text) AS final_note_len
                FROM f5_analytics WHERE user_id = ? ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            for r in r5:
                metrics = {}
                try:
                    m = json.loads(r["metrics_json"] or "{}")
                    if isinstance(m, dict):
                        metrics = m
                except Exception:
                    metrics = {}
                out["f5"].append(
                    {
                        "conversation_id": r["conversation_id"],
                        "project_id": r["project_id"] or "",
                        "dialogue_id": r["dialogue_id"] or "",
                        "updated_at": int(r["updated_at"] or 0),
                        "metrics": metrics,
                        "review_char_len": int(r["review_len"] or 0),
                        "final_note_char_len": int(r["final_note_len"] or 0),
                    }
                )
        finally:
            conn.close()
    return out

