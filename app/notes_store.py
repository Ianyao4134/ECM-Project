from __future__ import annotations

import json
import os
from typing import Any

from .config import settings


def _notes_path() -> str:
    return os.path.join(settings.data_dir, "notes.json")


def load_notes() -> dict[str, Any]:
    path = _notes_path()
    if not os.path.isfile(path):
        return {"topic": "", "tags": [], "quotes": [], "hooks": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_notes(notes: dict[str, Any]) -> None:
    os.makedirs(settings.data_dir, exist_ok=True)
    path = _notes_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


def merge_notes(base: dict[str, Any], *, topic: str | None, tags: list[str], quotes: list[str], hooks: list[str]) -> dict[str, Any]:
    out = dict(base or {})
    out.setdefault("topic", "")
    out.setdefault("tags", [])
    out.setdefault("quotes", [])
    out.setdefault("hooks", [])

    if topic and topic.strip():
        out["topic"] = topic.strip()

    def _extend_unique(key: str, items: list[str]) -> None:
        existing = out.get(key) or []
        seen = set(existing)
        for it in items:
            if it not in seen:
                existing.append(it)
                seen.add(it)
        out[key] = existing

    _extend_unique("tags", tags)
    _extend_unique("quotes", quotes)
    _extend_unique("hooks", hooks)
    return out

