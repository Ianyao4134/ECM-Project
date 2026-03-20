"""User profile store for student personalization and persona building."""

from __future__ import annotations

import json
import os
from typing import Any

from .config import settings


def _profiles_path() -> str:
    return os.path.join(settings.data_dir, "profiles.json")


def _load_profiles() -> dict[str, dict[str, Any]]:
    path = _profiles_path()
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _save_profiles(profiles: dict[str, dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(_profiles_path()), exist_ok=True)
    with open(_profiles_path(), "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)


def get_profile(user_id: str) -> dict[str, Any]:
    """Get user profile. Returns empty dict if not found."""
    if not user_id:
        return {}
    profiles = _load_profiles()
    return profiles.get(user_id, {})


def save_profile(user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Save user profile. Normalizes keys and keeps persona builder output."""
    if not user_id:
        return {}
    profiles = _load_profiles()
    prev = profiles.get(user_id, {}) if isinstance(profiles.get(user_id), dict) else {}
    normalized = {
        "age": str(profile.get("age", "")).strip(),
        "stage": str(profile.get("stage", "")).strip(),
        "major": str(profile.get("major", "")).strip(),
        "interests": str(profile.get("interests", "")).strip(),
        "hobbies": str(profile.get("hobbies", "")).strip(),
        # persona builder (optional)
        "core_motivation": str(profile.get("core_motivation", prev.get("core_motivation", ""))).strip(),
        "end_goal": str(profile.get("end_goal", prev.get("end_goal", ""))).strip(),
        "learning_habits": str(profile.get("learning_habits", prev.get("learning_habits", ""))).strip(),
        "persona_summary": str(profile.get("persona_summary", prev.get("persona_summary", ""))).strip(),
        "persona_transcript": profile.get("persona_transcript", prev.get("persona_transcript", [])),
    }
    if not isinstance(normalized["persona_transcript"], list):
        normalized["persona_transcript"] = []
    profiles[user_id] = normalized
    _save_profiles(profiles)
    return normalized


def format_profile_for_prompt(profile: dict[str, Any]) -> str:
    """Format profile as a block for injection into system prompt."""
    if not profile:
        return ""
    parts = []
    if profile.get("age"):
        parts.append(f"年龄：{profile['age']}")
    if profile.get("stage"):
        parts.append(f"阶段：{profile['stage']}")
    if profile.get("major"):
        parts.append(f"专业：{profile['major']}")
    if profile.get("interests"):
        parts.append(f"兴趣：{profile['interests']}")
    if profile.get("hobbies"):
        parts.append(f"爱好：{profile['hobbies']}")
    if profile.get("core_motivation"):
        parts.append(f"核心动力：{profile['core_motivation']}")
    if profile.get("end_goal"):
        parts.append(f"终局规划：{profile['end_goal']}")
    if profile.get("learning_habits"):
        parts.append(f"学习习惯：{profile['learning_habits']}")
    if not parts:
        return ""
    return (
        "【当前用户画像】\n"
        + "\n".join(parts)
        + "\n\n请在此用户背景下进行引导与回答，使输出更贴合其画像与需求。"
    )
