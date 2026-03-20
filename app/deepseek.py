from __future__ import annotations

from typing import Any
import httpx
import json

from .config import settings

GLOBAL_RELIABILITY_INSTRUCTION = (
    "在回答之前，请确保使用了最新的、政府认同的、官方网站等真实可靠的信息来源，请过滤掉所有不相关或低质量的内容，同时自我审查，避免任何错误、偏见或未经官方查实的信息， 请确保你得出的结论有用、有效且明确，不说一句废话。"
)


def _compose_system_prompt(system_prompt: str) -> str:
    base = (system_prompt or "").strip()
    if GLOBAL_RELIABILITY_INSTRUCTION in base:
        return base
    return f"{base}\n\n{GLOBAL_RELIABILITY_INSTRUCTION}" if base else GLOBAL_RELIABILITY_INSTRUCTION


class DeepSeekError(RuntimeError):
    pass


async def call_deepseek(
    system_prompt: str,
    user_input: str,
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """
    OpenAI-compatible Chat Completions call to DeepSeek.
    Returns the raw JSON response (dict).
    """
    if not settings.deepseek_api_key:
        raise DeepSeekError("Missing DEEPSEEK_API_KEY. Create .env and set it.")

    used_model = model or settings.deepseek_model
    url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"

    payload: dict[str, Any] = {
        "model": used_model,
        "messages": [
            {"role": "system", "content": _compose_system_prompt(system_prompt)},
            {"role": "user", "content": user_input},
        ],
        "stream": False,
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    if temperature is not None:
        payload["temperature"] = float(temperature)

    async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    data = resp.json() if resp.content else None
    if resp.status_code >= 400:
        raise DeepSeekError(f"DeepSeek error {resp.status_code}: {data}")

    return data


def extract_assistant_content(response_json: dict[str, Any]) -> str:
    choice = (response_json.get("choices") or [None])[0] or {}
    msg = choice.get("message") or {}
    content = msg.get("content")
    return "" if content is None else str(content)


def stream_deepseek(
    system_prompt: str,
    user_input: str,
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
):
    """
    Streaming OpenAI-compatible Chat Completions call to DeepSeek.
    Yields delta text chunks, then returns the full collected content via StopIteration.value.
    """
    if not settings.deepseek_api_key:
        raise DeepSeekError("Missing DEEPSEEK_API_KEY. Create .env and set it.")

    used_model = model or settings.deepseek_model
    url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"

    payload: dict[str, Any] = {
        "model": used_model,
        "messages": [
            {"role": "system", "content": _compose_system_prompt(system_prompt)},
            {"role": "user", "content": user_input},
        ],
        "stream": True,
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    if temperature is not None:
        payload["temperature"] = float(temperature)

    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    collected: list[str] = []

    with httpx.Client(timeout=settings.request_timeout_s) as client:
        with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code >= 400:
                try:
                    data = resp.json()
                except Exception:
                    data = resp.text
                raise DeepSeekError(f"DeepSeek error {resp.status_code}: {data}")

            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    evt = json.loads(data_str)
                except Exception:
                    continue

                choice = (evt.get("choices") or [None])[0] or {}
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                if piece:
                    text_piece = str(piece)
                    collected.append(text_piece)
                    yield text_piece

    return "".join(collected)

