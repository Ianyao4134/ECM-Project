from __future__ import annotations

import os

from .config import settings


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_prompt(name: str) -> str:
    """
    Load a prompt file from prompts/ by filename.
    """
    path = os.path.join(settings.prompts_dir, name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Prompt not found: {path}")
    return _read_text(path)


def build_system_prompt(*parts: str) -> str:
    return "\n\n".join([p.strip() for p in parts if p and p.strip()]).strip()

