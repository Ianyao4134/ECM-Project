from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
import threading
import time
import uuid
import os
import json
import sqlite3


Module1Step = int
Module2Step = int
Module4State = Literal["draft", "awaiting_confirm", "confirmed"]
Module5State = Literal["draft", "done"]


@dataclass
class Module1Session:
    session_id: str
    created_at: float = field(default_factory=time.time)
    step: Module1Step = 1
    topic: str = ""
    question: str = ""
    history: list[dict[str, str]] = field(default_factory=list)  # {role, content}
    done: bool = False
    awaiting_confirm: bool = False
    confirmed_definition: str = ""


_lock = threading.Lock()
_module1_sessions: dict[str, Module1Session] = {}
_module2_sessions: dict[str, "Module2Session"] = {}
_module4_sessions: dict[str, "Module4Session"] = {}
_module5_sessions: dict[str, "Module5Session"] = {}

_SESSIONS_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "sessions.db")


def _sessions_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_SESSIONS_DB_PATH), exist_ok=True)
    c = sqlite3.connect(_SESSIONS_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_module4_sessions_db() -> None:
    """
    Persist Module4 sessions so that after server restart we can still call
    /ecm/module4/confirm with the same session_id.
    """
    with _lock:
        conn = _sessions_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS module4_sessions (
                  session_id TEXT PRIMARY KEY,
                  created_at REAL NOT NULL,
                  definition TEXT NOT NULL DEFAULT '',
                  report_md TEXT NOT NULL DEFAULT '',
                  state TEXT NOT NULL DEFAULT 'draft',
                  history_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


@dataclass
class Module2Session:
    session_id: str
    created_at: float = field(default_factory=time.time)
    step: Module2Step = 1
    definition: str = ""
    history: list[dict[str, str]] = field(default_factory=list)
    done: bool = False
    # tree dialog
    root_id: str = ""
    nodes: dict[str, dict[str, object]] = field(default_factory=dict)  # node_id -> {id,parent_id,action,step,user,assistant,score,reference,ts}

    def ensure_root(self) -> str:
        if self.root_id:
            return self.root_id
        rid = str(uuid.uuid4())
        self.root_id = rid
        self.nodes[rid] = {"id": rid, "parent_id": None, "action": "root", "step": int(self.step), "ts": time.time()}
        return rid


@dataclass
class Module4Session:
    session_id: str
    created_at: float = field(default_factory=time.time)
    definition: str = ""
    report_md: str = ""
    state: Module4State = "draft"
    history: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Module5Session:
    session_id: str
    created_at: float = field(default_factory=time.time)
    module4_session_id: str = ""
    output_md: str = ""
    state: Module5State = "draft"


def new_module1_session(*, question: str, topic: str | None = None) -> Module1Session:
    sid = str(uuid.uuid4())
    s = Module1Session(session_id=sid, question=question.strip(), topic=(topic or "").strip())
    with _lock:
        _module1_sessions[sid] = s
    return s


def get_module1_session(session_id: str) -> Module1Session | None:
    with _lock:
        return _module1_sessions.get(session_id)


def save_module1_session(session: Module1Session) -> None:
    with _lock:
        _module1_sessions[session.session_id] = session


def new_module2_session(*, definition: str) -> Module2Session:
    sid = str(uuid.uuid4())
    s = Module2Session(session_id=sid, definition=definition.strip())
    with _lock:
        _module2_sessions[sid] = s
    return s


def get_module2_session(session_id: str) -> Module2Session | None:
    with _lock:
        return _module2_sessions.get(session_id)


def save_module2_session(session: Module2Session) -> None:
    with _lock:
        _module2_sessions[session.session_id] = session


def new_module4_session(*, definition: str, report_md: str) -> Module4Session:
    sid = str(uuid.uuid4())
    s = Module4Session(session_id=sid, definition=definition.strip(), report_md=report_md)
    with _lock:
        _module4_sessions[sid] = s
        # Persist immediately so the same sid survives server restart.
        try:
            conn = _sessions_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO module4_sessions
                      (session_id, created_at, definition, report_md, state, history_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                      created_at=excluded.created_at,
                      definition=excluded.definition,
                      report_md=excluded.report_md,
                      state=excluded.state,
                      history_json=excluded.history_json
                    """,
                    (
                        s.session_id,
                        s.created_at,
                        s.definition,
                        s.report_md,
                        s.state,
                        json.dumps(s.history, ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            # Never block the main flow due to persistence.
            pass
    return s


def get_module4_session(session_id: str) -> Module4Session | None:
    with _lock:
        s = _module4_sessions.get(session_id)
        if s:
            return s

    # Try load from SQLite outside the in-memory lock
    try:
        conn = _sessions_conn()
        try:
            row = conn.execute(
                """
                SELECT session_id, created_at, definition, report_md, state, history_json
                FROM module4_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None

        history: list[dict[str, str]] = []
        try:
            raw = row["history_json"] or "[]"
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                history = [x for x in parsed if isinstance(x, dict)]
        except Exception:
            history = []

        s2 = Module4Session(
            session_id=str(row["session_id"]),
            created_at=float(row["created_at"] or time.time()),
            definition=str(row["definition"] or ""),
            report_md=str(row["report_md"] or ""),
            state=str(row["state"] or "draft"),  # type: ignore[arg-type]
            history=history,
        )
        with _lock:
            _module4_sessions[s2.session_id] = s2
        return s2
    except Exception:
        return None


def save_module4_session(session: Module4Session) -> None:
    with _lock:
        _module4_sessions[session.session_id] = session
        # Persist the latest snapshot.
        try:
            conn = _sessions_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO module4_sessions
                      (session_id, created_at, definition, report_md, state, history_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                      created_at=excluded.created_at,
                      definition=excluded.definition,
                      report_md=excluded.report_md,
                      state=excluded.state,
                      history_json=excluded.history_json
                    """,
                    (
                        session.session_id,
                        session.created_at,
                        session.definition,
                        session.report_md,
                        session.state,
                        json.dumps(session.history, ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass


def new_module5_session(*, module4_session_id: str, output_md: str) -> Module5Session:
    sid = str(uuid.uuid4())
    s = Module5Session(session_id=sid, module4_session_id=module4_session_id, output_md=output_md)
    with _lock:
        _module5_sessions[sid] = s
    return s


def get_module5_session(session_id: str) -> Module5Session | None:
    with _lock:
        return _module5_sessions.get(session_id)


def save_module5_session(session: Module5Session) -> None:
    with _lock:
        _module5_sessions[session.session_id] = session

