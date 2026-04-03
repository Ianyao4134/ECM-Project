"""
Copy committed seed JSON into ECM_DATA_DIR on first run, and insert sample analytics
when the analytics DB is empty. Disabled with ECM_DISABLE_SEED=1.

Seed credentials are for testing only (see seed/data/users.json).
"""

from __future__ import annotations

import json
import os
import shutil

from .analytics_store import (
    is_analytics_seedable,
    upsert_f1_analytics,
    upsert_f2_analytics,
    upsert_f3_analytics,
    upsert_f4_analytics,
    upsert_f5_analytics,
)
from .config import settings

_SEED_USER = "00000000-0000-4000-8000-000000000001"
_SEED_PROJECT = "00000000-0000-4000-8000-000000000002"
_SEED_DIALOGUE = "00000000-0000-4000-8000-000000000003"
_TS = 1730000000000


def _seed_dir() -> str:
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "seed", "data"))


def _copy_seed_json_if_missing() -> None:
    src_dir = _seed_dir()
    if not os.path.isdir(src_dir):
        return
    dst = settings.data_dir
    users_dst = os.path.join(dst, "users.json")
    if os.path.isfile(users_dst):
        return
    os.makedirs(dst, exist_ok=True)
    for name in ("users.json", "projects.json", "profiles.json", "notes.json"):
        s = os.path.join(src_dir, name)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(dst, name))


def _seed_demo_user_present() -> bool:
    path = os.path.join(settings.data_dir, "users.json")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            users = json.load(f)
    except Exception:
        return False
    if not isinstance(users, list):
        return False
    for u in users:
        if isinstance(u, dict) and str(u.get("id") or "") == _SEED_USER:
            return True
    return False


def _insert_sample_analytics() -> None:
    if not is_analytics_seedable() or not _seed_demo_user_present():
        return
    cid = _SEED_DIALOGUE
    uid = _SEED_USER
    pid = _SEED_PROJECT
    did = _SEED_DIALOGUE

    history_sample = [
        {"role": "user", "content": "你好，我想讨论学习动机相关的问题。"},
        {"role": "assistant", "content": "我们可以从具体情境出发，先梳理你最近的学习体验。"},
    ]
    metrics_common = {"rounds": 2, "latency_ms": 1200, "seed": 1}

    upsert_f1_analytics(
        conversation_id=cid,
        user_id=uid,
        project_id=pid,
        dialogue_id=did,
        history=history_sample,
        metrics=metrics_common,
        updated_at_ms=_TS,
    )
    upsert_f2_analytics(
        conversation_id=cid,
        user_id=uid,
        project_id=pid,
        dialogue_id=did,
        history=history_sample,
        metrics={**metrics_common, "branch_depth": 1},
        updated_at_ms=_TS + 1,
    )
    upsert_f3_analytics(
        conversation_id=cid,
        user_id=uid,
        project_id=pid,
        dialogue_id=did,
        note_text="【种子】示例笔记内容。",
        cards=[{"title": "示例卡片", "body": "种子数据"}],
        metrics={**metrics_common, "note_chars": 12},
        updated_at_ms=_TS + 2,
    )
    upsert_f4_analytics(
        conversation_id=cid,
        user_id=uid,
        project_id=pid,
        dialogue_id=did,
        report_text="【种子】示例阶段报告摘要。",
        metrics={**metrics_common, "report_chars": 18},
        updated_at_ms=_TS + 3,
    )
    upsert_f5_analytics(
        conversation_id=cid,
        user_id=uid,
        project_id=pid,
        dialogue_id=did,
        ai_review_text="【种子】示例 AI 回顾。",
        final_note_text="【种子】示例终稿笔记。",
        metrics={**metrics_common, "review_chars": 14},
        updated_at_ms=_TS + 4,
    )


def apply_seed_data_if_needed() -> None:
    v = (os.getenv("ECM_DISABLE_SEED") or "").strip().lower()
    if v in ("1", "true", "yes"):
        return
    _copy_seed_json_if_missing()
    _insert_sample_analytics()
