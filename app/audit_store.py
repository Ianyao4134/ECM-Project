from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Any

_LOCK = threading.Lock()
# Same SQLite file as analytics (one DB, extra table).
_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "analytics.db")


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_audit_db() -> None:
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts INTEGER NOT NULL,
                  method TEXT NOT NULL,
                  path TEXT NOT NULL,
                  query TEXT,
                  ip TEXT,
                  user_agent TEXT,
                  user_id TEXT,
                  username TEXT,
                  status_code INTEGER
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
            conn.commit()
        finally:
            conn.close()


def append_audit_row(
    *,
    method: str,
    path: str,
    query: str,
    ip: str,
    user_agent: str,
    user_id: str,
    username: str,
    status_code: int,
) -> None:
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                """
                INSERT INTO audit_log
                  (ts, method, path, query, ip, user_agent, user_id, username, status_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time() * 1000),
                    method[:16],
                    path[:2048],
                    (query or "")[:2000],
                    (ip or "")[:128],
                    (user_agent or "")[:512],
                    (user_id or "")[:128],
                    (username or "")[:128],
                    int(status_code),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def list_audit(*, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                """
                SELECT id, ts, method, path, query, ip, user_agent, user_id, username, status_code
                FROM audit_log
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        finally:
            conn.close()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "ts": r["ts"],
                "method": r["method"],
                "path": r["path"],
                "query": r["query"] or "",
                "ip": r["ip"] or "",
                "user_agent": r["user_agent"] or "",
                "user_id": r["user_id"] or "",
                "username": r["username"] or "",
                "status_code": r["status_code"],
            }
        )
    return out


def analytics_table_counts() -> dict[str, int]:
    tables = ("f1_analytics", "f2_analytics", "f3_analytics", "f4_analytics", "f5_analytics")
    out: dict[str, int] = {}
    with _LOCK:
        conn = _conn()
        try:
            for t in tables:
                try:
                    row = conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()
                    out[t] = int(row["c"]) if row else 0
                except Exception:
                    out[t] = 0
        finally:
            conn.close()
    return out


def list_recent_analytics_rows(*, module: str, limit: int = 30) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    m = (module or "").strip().lower()
    with _LOCK:
        conn = _conn()
        try:
            if m == "f1":
                rows = conn.execute(
                    """
                    SELECT conversation_id, user_id, project_id, dialogue_id, updated_at,
                           length(history_json) AS payload_bytes
                    FROM f1_analytics
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            elif m == "f2":
                rows = conn.execute(
                    """
                    SELECT conversation_id, user_id, project_id, dialogue_id, updated_at,
                           length(history_json) AS payload_bytes
                    FROM f2_analytics
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            elif m == "f3":
                rows = conn.execute(
                    """
                    SELECT conversation_id, user_id, project_id, dialogue_id, updated_at,
                           length(note_text) AS note_len,
                           length(cards_json) AS cards_bytes
                    FROM f3_analytics
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            elif m == "f4":
                rows = conn.execute(
                    """
                    SELECT conversation_id, user_id, project_id, dialogue_id, updated_at,
                           length(report_text) AS report_len
                    FROM f4_analytics
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            elif m == "f5":
                rows = conn.execute(
                    """
                    SELECT conversation_id, user_id, project_id, dialogue_id, updated_at,
                           length(ai_review_text) AS review_len,
                           length(final_note_text) AS note_len
                    FROM f5_analytics
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                return []
        finally:
            conn.close()
    result: list[dict[str, Any]] = []
    for r in rows:
        d = {k: r[k] for k in r.keys()}
        result.append(d)
    return result
