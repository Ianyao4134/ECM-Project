from __future__ import annotations

from dotenv import load_dotenv
import os
from dataclasses import dataclass


load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Railway 里有时 `DEEPSEEK_API_KEY` 是只读 Secret，我们允许兜底读取 `DEEPSEEK_API_KEY_2`
    deepseek_api_key: str | None = (os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY_2") or "").strip() or None
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    request_timeout_s: float = float(os.getenv("DEEPSEEK_TIMEOUT_S", "60"))

    prompts_dir: str = os.getenv("ECM_PROMPTS_DIR", os.path.join(os.getcwd(), "prompts"))
    data_dir: str = os.getenv("ECM_DATA_DIR", os.path.join(os.getcwd(), "data"))

    # Owner-only audit console (set in production). Empty = admin API disabled.
    ecm_admin_secret: str | None = os.getenv("ECM_ADMIN_SECRET")


settings = Settings()

