from __future__ import annotations

from dotenv import load_dotenv
import os
from dataclasses import dataclass


load_dotenv()


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str | None = os.getenv("DEEPSEEK_API_KEY")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    request_timeout_s: float = float(os.getenv("DEEPSEEK_TIMEOUT_S", "60"))

    prompts_dir: str = os.getenv("ECM_PROMPTS_DIR", os.path.join(os.getcwd(), "prompts"))
    data_dir: str = os.getenv("ECM_DATA_DIR", os.path.join(os.getcwd(), "data"))


settings = Settings()

