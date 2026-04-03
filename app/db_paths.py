"""
Resolve SQLite paths under ECM_DATA_DIR so one Railway volume on /app/data
persists JSON + analytics.db + sessions.db together.

Legacy: app/data/*.db (still used if present and no file in data_dir yet).
"""

from __future__ import annotations

import os

from .config import settings


def _legacy_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "data")


def analytics_db_path() -> str:
    preferred = os.path.join(settings.data_dir, "analytics.db")
    legacy = os.path.join(_legacy_dir(), "analytics.db")
    if os.path.isfile(preferred):
        return preferred
    if os.path.isfile(legacy):
        return legacy
    return preferred


def sessions_db_path() -> str:
    preferred = os.path.join(settings.data_dir, "sessions.db")
    legacy = os.path.join(_legacy_dir(), "sessions.db")
    if os.path.isfile(preferred):
        return preferred
    if os.path.isfile(legacy):
        return legacy
    return preferred
