from __future__ import annotations

import re
from dataclasses import dataclass


_TAG_RE = re.compile(r"#([0-9A-Za-z_]+|[\u4e00-\u9fff]+)")
_QUOTE_RE = re.compile(r"“([^”]{1,400})”|\"([^\"]{1,400})\"")
_HOOK_LINE_RE = re.compile(r"^\s*(?:HOOK|钩子|抓手)\s*[:：]\s*(.+?)\s*$", re.IGNORECASE)
_CARD_TAGS_RE = re.compile(r"(?:🏷️\s*)?关键词\s*/?\s*Tags?\s*[:：]\s*(.+)$", re.IGNORECASE)
_CARD_QUOTE_RE = re.compile(r"核心金句\s*[:：]\s*(.+)$")
_CARD_HOOK_RE = re.compile(r"记忆钩子\s*[:：]\s*(.+)$")
_MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*([\s\S]*?)```", re.IGNORECASE)


@dataclass(frozen=True)
class Extracted:
    tags: list[str]
    quotes: list[str]
    hooks: list[str]


def extract_tags_quotes_hooks(text: str) -> Extracted:
    tags = []
    seen = set()
    for m in _TAG_RE.finditer(text or ""):
        t = m.group(0)
        if t not in seen:
            tags.append(t)
            seen.add(t)

    quotes = []
    seen_q = set()
    for m in _QUOTE_RE.finditer(text or ""):
        q = m.group(1) or m.group(2) or ""
        q = q.strip()
        if q and q not in seen_q:
            quotes.append(q)
            seen_q.add(q)

    hooks = []
    seen_h = set()
    for line in (text or "").splitlines():
        mm = _HOOK_LINE_RE.match(line)
        if not mm:
            continue
        h = mm.group(1).strip()
        if h and h not in seen_h:
            hooks.append(h)
            seen_h.add(h)

    return Extracted(tags=tags, quotes=quotes, hooks=hooks)


def extract_note_card(text: str) -> dict[str, object]:
    """
    Extract structured metadata from the '📌 笔记卡片' section if present.
    Returns: { "tags": [...], "quote": str|None, "hook": str|None }
    """
    tags: list[str] = []
    quote: str | None = None
    hook: str | None = None

    lines = (text or "").splitlines()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # tags line (flexible)
        tags_part: str | None = None
        m = _CARD_TAGS_RE.search(line)
        if m:
            tags_part = (m.group(1) or "").strip()
        elif "关键词" in line:
            # 兼容：有些模型会输出 "🏷️ 关键词 #A #B"（无冒号）
            if "：" in line:
                tags_part = line.split("：", 1)[1].strip()
            elif ":" in line:
                tags_part = line.split(":", 1)[1].strip()
            else:
                idx = line.find("关键词")
                if idx >= 0:
                    tags_part = line[idx + len("关键词") :].strip()

        if tags_part is not None:
            # 优先提取带 # 的标签（严格格式）
            tags = [t.group(0) for t in _TAG_RE.finditer(tags_part)]
            # 兼容：若模型没输出 #，则按分隔符拆词并补上 #
            if not tags:
                cleaned = re.sub(r"[\[\]【】()（）<>《》“”\"'🏷️]", " ", tags_part)
                parts = re.split(r"[\s,，;；、|/]+", cleaned)
                parts = [p.strip() for p in parts if p and p.strip()]
                parts = parts[:10]
                tags = [p if p.startswith("#") else f"#{p}" for p in parts]
            continue

        # quote line
        m = _CARD_QUOTE_RE.search(line)
        if m and quote is None:
            qline = m.group(1).strip()
            mq = _QUOTE_RE.search(qline)
            if mq:
                quote = (mq.group(1) or mq.group(2) or "").strip()
            else:
                quote = qline.strip("[]【】 ")
            continue

        # hook line
        m = _CARD_HOOK_RE.search(line)
        if m and hook is None:
            hline = m.group(1).strip()
            mh = _HOOK_LINE_RE.match(hline)
            if mh:
                hook = mh.group(1).strip()
            else:
                # accept plain text
                hook = hline
            continue

    return {"tags": tags, "quote": quote, "hook": hook}


def strip_note_card_block(text: str) -> str:
    """
    Remove the '📌 笔记卡片 (交互区)' block from text so Function 2 only shows
    深度解析 + 导师提问.
    """
    if not text or "📌" not in text or "👉" not in text:
        return text

    i = text.find("📌")
    j = text.find("👉", i)
    if j < 0:
        return text

    before = text[:i].rstrip()
    after = text[j:].lstrip()
    out = (before + "\n\n" + after).strip()
    return out if out else text


def extract_mermaid_code(text: str) -> str | None:
    m = _MERMAID_BLOCK_RE.search(text or "")
    if not m:
        return None
    code = (m.group(1) or "").strip()
    return code or None

