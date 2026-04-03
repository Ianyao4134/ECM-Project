from __future__ import annotations

from flask import Flask, jsonify, request, Response, stream_with_context
from waitress import serve
import asyncio
import os
import json
import re
import time
import uuid
from datetime import datetime, timezone
import io
import zipfile
from html import escape as _html_escape
from typing import Any
import xml.etree.ElementTree as ET
import base64
import hmac
from collections import Counter

from .config import settings
from .ecm_engine import run_ecm
from .deepseek import call_deepseek, extract_assistant_content, stream_deepseek
from .prompts import build_system_prompt, load_prompt
from .parsing import extract_mermaid_code, extract_note_card, extract_tags_quotes_hooks, strip_note_card_block
from .notes_store import load_notes, merge_notes, save_notes
from .profiles_store import format_profile_for_prompt, get_profile, save_profile
from .analytics_store import (
    init_analytics_db,
    upsert_f1_analytics,
    get_f1_analytics,
    upsert_f3_analytics,
    get_f3_analytics,
    upsert_f2_analytics,
    get_f2_analytics,
    upsert_f4_analytics,
    get_f4_analytics,
    upsert_f5_analytics,
    get_f5_analytics,
    list_all_analytics_for_user,
)
from .projects_store import (
    create_user,
    create_dialogue,
    list_projects,
    list_dialogues,
    load_dialogue,
    load_project,
    load_projects,
    load_users,
    save_dialogue,
    save_project,
    upsert_user,
)
from .audit_store import (
    init_audit_db,
    append_audit_row,
    list_audit,
    analytics_table_counts,
    list_recent_analytics_rows,
    list_audit_for_user,
)
from .config import settings as _settings_for_prompts
from .seed_bootstrap import apply_seed_data_if_needed, restore_baked_data_if_empty
from .sessions import (
    get_module1_session,
    get_module2_session,
    get_module4_session,
    get_module5_session,
    new_module1_session,
    new_module2_session,
    new_module4_session,
    new_module5_session,
    save_module1_session,
    save_module2_session,
    save_module4_session,
    save_module5_session,
    init_module4_sessions_db,
)


app = Flask("ecm-thinking-engine")
restore_baked_data_if_empty()
init_analytics_db()
init_module4_sessions_db()
init_audit_db()
apply_seed_data_if_needed()


def _client_ip() -> str:
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip()[:128]
    return (request.remote_addr or "")[:128]


def _audit_extract_identity() -> tuple[str, str]:
    uid = (request.args.get("userId") or request.args.get("user_id") or "").strip()
    uname = ""
    body = request.get_json(silent=True)
    if isinstance(body, dict):
        uid = uid or str(body.get("userId") or body.get("user_id") or "").strip()
        uname = str(body.get("username") or "").strip()
    return uid[:128], uname[:128]


@app.after_request
def _audit_after(response: Response):
    try:
        p = request.path or ""
        if not p.startswith("/ecm/"):
            return response
        if p.startswith("/ecm/admin"):
            return response
        if request.method == "OPTIONS":
            return response
        uid, uname = _audit_extract_identity()
        q = request.query_string.decode("utf-8", errors="replace") if request.query_string else ""
        ua = (request.headers.get("User-Agent") or "")[:512]
        append_audit_row(
            method=request.method,
            path=p,
            query=q,
            ip=_client_ip(),
            user_agent=ua,
            user_id=uid,
            username=uname,
            status_code=response.status_code,
        )
    except Exception:
        pass
    return response


@app.errorhandler(Exception)
def _handle_unexpected_exception(e: Exception):
    """
    Ensure we always return JSON for unexpected errors (so the frontend can show details).
    """
    return jsonify({"error": "Internal Server Error", "detail": str(e) or "unknown"}), 500


@app.errorhandler(500)
def _handle_500(_e):
    return jsonify({"error": "Internal Server Error", "detail": "server_500"}), 500

_SCORE_RE = re.compile(r"\[Score\]\s*[:：]\s*(\d{1,2})")
_REF_RE = re.compile(r"\[Reference\]\s*[:：]\s*(.+)")

_JSON_LEFT = "{"
_JSON_RIGHT = "}"


def _escape_xml(text: str) -> str:
    # WordprocessingML uses xml entities; also keep whitespace via xml:space in <w:t>.
    # We escape &, <, > and quotes just in case.
    return _html_escape(text, quote=True).replace("'", "&apos;")


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """
    Best-effort: extract the first JSON object from model output.
    """
    if not text:
        return None
    s = text.strip()
    # If it's already JSON
    if s.startswith(_JSON_LEFT) and s.endswith(_JSON_RIGHT):
        try:
            v = json.loads(s)
            if isinstance(v, dict):
                return v
        except Exception:
            pass
    # Try substring extraction
    li = s.find(_JSON_LEFT)
    ri = s.rfind(_JSON_RIGHT)
    if li >= 0 and ri > li:
        cand = s[li : ri + 1]
        try:
            v = json.loads(cand)
            if isinstance(v, dict):
                return v
        except Exception:
            return None
    return None


def _build_min_docx_two_col_table(*, title: str, rows: list[list[dict[str, Any]]]) -> bytes:
    """
    Build a minimal .docx with a 2-column table and merged cells via w:gridSpan.

    rows example:
      [
        [ { "span": 2, "paragraphs": [...] } ],
        [ { "span": 1, ... }, { "span": 1, ... } ],
        [ { "span": 1, ... }, { "span": 1, ... } ],
      ]
    Each cell dict:
      - span: 1|2
      - paragraphs: list[str]  (each becomes a <w:p>)
    """

    # Word uses dxa units. We'll use 2500 for each column -> 5000 total.
    col_w = 2500
    table_w = col_w * 2

    def cell_xml(cell: dict[str, Any], cell_idx: int) -> str:
        span = 1 if cell.get("span") != 2 else 2
        w = table_w if span == 2 else col_w
        paras: list[str] = []
        raw_paras = cell.get("paragraphs")
        if isinstance(raw_paras, list):
            paras = [p for p in raw_paras if p is not None]
        if not paras:
            paras = [""]

        grid_span_xml = ""
        if span == 2:
            grid_span_xml = f"<w:tcPr><w:gridSpan w:val=\"2\"/><w:tcW w:w=\"{w}\" w:type=\"dxa\"/><w:tcBorders>"
        else:
            grid_span_xml = f"<w:tcPr><w:tcW w:w=\"{w}\" w:type=\"dxa\"/><w:tcBorders>"

        # Simple borders inside each cell.
        borders = (
            '<w:top w:val="single" w:sz="8" w:color="000000"/>'
            '<w:left w:val="single" w:sz="8" w:color="000000"/>'
            '<w:bottom w:val="single" w:sz="8" w:color="000000"/>'
            '<w:right w:val="single" w:sz="8" w:color="000000"/>'
        )

        tc_pr_open = grid_span_xml
        tc_pr_close = f"</w:tcBorders></w:tcPr>"

        # Build paragraphs
        p_xmls: list[str] = []
        for p in paras:
            bold = False
            text = ""
            if isinstance(p, dict):
                text = _safe_str(p.get("text")).strip()
                bold = bool(p.get("bold"))
            else:
                text = _safe_str(p).strip()

            if bold:
                p_xmls.append(
                    "<w:p><w:r><w:rPr><w:b/></w:rPr><w:t xml:space=\"preserve\">"
                    + _escape_xml(text)
                    + "</w:t></w:r></w:p>"
                )
            else:
                p_xmls.append(
                    "<w:p><w:r><w:t xml:space=\"preserve\">"
                    + _escape_xml(text)
                    + "</w:t></w:r></w:p>"
                )

        return f"<w:tc>{tc_pr_open}{borders}{tc_pr_close}{''.join(p_xmls)}</w:tc>"

    # Paragraph for title
    title_xml = (
        "<w:p><w:r><w:t xml:space=\"preserve\">"
        + _escape_xml(title or "")
        + "</w:t></w:r></w:p>"
    )

    # Table XML
    tbl_borders = (
        '<w:top w:val="single" w:sz="8" w:color="000000"/>'
        '<w:left w:val="single" w:sz="8" w:color="000000"/>'
        '<w:bottom w:val="single" w:sz="8" w:color="000000"/>'
        '<w:right w:val="single" w:sz="8" w:color="000000"/>'
        '<w:insideH w:val="single" w:sz="8" w:color="000000"/>'
        '<w:insideV w:val="single" w:sz="8" w:color="000000"/>'
    )

    # grid
    grid_xml = f"<w:tblGrid><w:gridCol w:w=\"{col_w}\"/><w:gridCol w:w=\"{col_w}\"/></w:tblGrid>"

    tr_xmls: list[str] = []
    for r_idx, row_cells in enumerate(rows):
        tcs: list[str] = []
        for c_idx, cell in enumerate(row_cells):
            tcs.append(cell_xml(cell, c_idx))
        tr_xmls.append(f"<w:tr>{''.join(tcs)}</w:tr>")

    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {title_xml}
    <w:tbl>
      <w:tblPr>
        <w:tblW w:w="{table_w}" w:type="dxa"/>
        <w:tblBorders>{tbl_borders}</w:tblBorders>
      </w:tblPr>
      {grid_xml}
      {''.join(tr_xmls)}
    </w:tbl>
  </w:body>
</w:document>
"""

    # Minimal styles/settings
    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:rPr>
      <w:sz w:val="22"/>
      <w:szCs w:val="22"/>
    </w:rPr>
  </w:style>
</w:styles>
"""

    settings_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:zoom w:percent="100"/>
</w:settings>
"""

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
</Types>
"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
</Relationships>
"""

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/styles.xml", styles_xml)
        z.writestr("word/settings.xml", settings_xml)
        z.writestr("word/_rels/document.xml.rels", doc_rels)

    return mem.getvalue()


def _extract_scores(text: str) -> list[int]:
    if not text:
        return []
    return [int(m.group(1)) for m in _SCORE_RE.finditer(text or "") if m and m.group(1)]


def _safe_str(x: object) -> str:
    try:
        if x is None:
            return ""
        if isinstance(x, str):
            return x
        return str(x)
    except Exception:
        return ""


def _history_role_messages(history: object) -> list[dict[str, str]]:
    """
    Normalize history into [{role: 'user'|'assistant', content: '...'}].
    Accepts arbitrary dict structures from saved project state.
    """
    if not history or not isinstance(history, list):
        return []
    out: list[dict[str, str]] = []
    for m in history:
        if not isinstance(m, dict):
            continue
        role = _safe_str(m.get("role")).strip()
        content = _safe_str(m.get("content")).strip()
        if not role or not content:
            continue
        if role not in ("user", "assistant"):
            continue
        out.append({"role": role, "content": content})
    return out


def _analyze_function_system_prompt(function_key: str) -> str:
    global_prompt = load_prompt("mentor_global_analysis.txt")
    # Function-specific requirements
    function_map: dict[str, str] = {
        "f1": (
            "Function 1（问题定义）分析要求：\n"
            "必须使用：布鲁姆认知目标分类学、话语分析/对话行为理论、自我决定理论、心流理论、认知负荷理论。\n"
            "重点：拆解学生初始问题认知层次与最终目标层次变化；分析提问/确认/复制/选项选择等行为序列；"
            "结合停留时间、思考时间、AI响应时间判断心流与认知负荷；评估AI个性化关联对学生内在动机的激发效果。\n"
            "学生反馈聚焦（极度重要）：观察证据必须主要引用学生的用户输入（role=user），不要以AI输出本身作为“学生反馈”。"
            "当 additional_metrics 中的 f1_student_feedback_provided 为 false（或无法确认）时，必须在观察证据与评价结论中明确指出：学生未给出对AI原文的实质性反馈（通常仅回复确认）。\n"
            "若 additional_metrics 中包含 f1_metrics_from_db，必须优先使用并在观察证据中给出具体数值佐证。\n"
            "输出格式（必须严格按以下顺序，每行一项）：\n"
            "理论应用：...\n"
            "观察证据：...\n"
            "评价结论：...\n"
            "改进建议：...\n"
            "最后一行必须是：基于【选择的理论】该学生【类似这样的结论】。\n"
        ),
        "f2": (
            "Function 2（深度探索）分析要求：\n"
            "必须使用：话语分析/对话行为理论、布鲁姆认知目标分类学、自我决定理论、序列模式挖掘。\n"
            "重点：分析用户在树状探索中的行为序列（提交 submit / 追问 followup）、确认/追问的分布、以及用户与AI的互动节奏（思考时间、等待与推进）。\n"
            "必须结合 Step 数量与分数 [Score]（如存在），并在观察证据与评价结论中给出分数分布/趋势（例如平均分、最高分、是否逐步上升）。\n"
            "学生反馈聚焦（极度重要）：评价时优先引用学生的 submit/followup 行为与其具体追问内容；[Score] 只作为“学生答案深度”的间接指标，不要把它当作AI自我叙述。"
            "当 additional_metrics 中的 f2_student_branch_feedback_provided 为 false 时，必须指出学生仅沿主干提交、缺少追问式反馈，导致深度扩展不足。\n"
            "若 additional_metrics 中包含 f2_metrics_from_db，必须优先使用并给出具体数值（如 avg_user_msg_length、avg_ai_msg_length、user_question_count、user_confirm_count、module_dwell_seconds、thinking_seconds_avg、ai_response_seconds_avg 等，如果存在）。\n"
            "输出格式（必须严格按以下顺序，每行一项）：\n"
            "理论应用：...\n"
            "观察证据：...\n"
            "评价结论：...\n"
            "改进建议：...\n"
            "最后一行必须是：基于【选择的理论】该学生【类似这样的结论】。\n"
        ),
        "f3": (
            "Function 3（笔记与知识共建）分析要求：\n"
            "必须使用：知识建构理论、布鲁姆认知目标分类学、反思性思维理论。\n"
            "重点：基于卡片数据分析知识主动建构程度、卡片认知层次分布、编辑前后差异与反思深度。\n"
            "学生反馈聚焦（极度重要）：仅把“学生编辑/修改卡片/标星/推送”视为有效反馈；AI生成内容仅用于对比。"
            "当 additional_metrics 中的 f3_student_edit_feedback_provided 为 false 时，必须明确指出：学生未对AI原文进行编辑反馈，导致知识共建动能不足。\n"
            "若 additional_metrics 中有 f3_metrics_from_db / f3_cards，必须优先使用，并在观察证据中给出具体数值（如卡片总数、编辑率、平均相似度、层次分布、重用行为）。\n"
            "输出格式（必须严格按以下顺序，每行一项）：\n"
            "理论应用：...\n"
            "观察证据：...\n"
            "评价结论：...\n"
            "改进建议：...\n"
            "最后一行必须是：基于【选择的理论】该学生【类似这样的结论】。\n"
        ),
        "f4": (
            "Function 4（洞察报告）分析要求：\n"
            "必须使用：知识建构理论、认知结构理论（通过报告结构/维度覆盖评估）。\n"
            "重点：评估学生对最终报告的整合与优化程度；"
            "检查最终报告是否覆盖“道法术器势”五个维度（若文本中出现相关关键词/结构视为覆盖）；"
            "若报告包含 Mermaid 或结构化图/条目变化线索，结合其变化判断思维结构化过程。\n"
            "学生反馈聚焦（极度重要）：评价重点必须落在学生对报告的确认/再生成请求（是否提供额外输入）和任何修改反馈，而不是落在AI报告本身。"
            "当 additional_metrics 中的 f4_student_feedback_provided 为 false 时，必须指出：学生未对AI原文给出实质反馈（通常仅确认、未追加修改）。\n"
            "若 additional_metrics 中包含 f4_metrics_from_db / f4_report_from_db，必须优先使用并在观察证据中给出具体数值（停留时间、修改次数、下载次数等）与最终报告覆盖情况。\n"
            "输出格式（必须严格按以下顺序，每行一项）：\n"
            "理论应用：...\n"
            "观察证据：...\n"
            "评价结论：...\n"
            "改进建议：...\n"
            "最后一行必须是：基于【选择的理论】该学生【类似这样的结论】。\n"
        ),
        "f5": (
            "Function 5（灵感与闭环）分析要求：\n"
            "必须使用：反思性思维理论、自我决定理论、情感计算。\n"
            "重点：基于笔记修改次数与最终字数评估反思深度；"
            "基于点击推荐主题/新建探索等行为（如 additional_metrics 中有）判断后续动机与自主性；"
            "基于 AI 点评文本情感倾向（积极/中性/消极）评估情感影响与可能的学习动能。\n"
            "学生反馈聚焦（极度重要）：只把学生的“笔记修改/点击推荐/新建探索”视为有效反馈；AI点评内容仅用于反推情感与动机。"
            "当 additional_metrics 中的 f5_student_feedback_provided 为 false 时，必须明确指出：学生未对AI原文进行反馈性修改或选择，闭环动能不足。\n"
            "若 additional_metrics 中包含 f5_metrics_from_db / f5_ai_review_from_db，必须优先使用并在观察证据中给出具体数值（修改次数、字数、停留时间、情感倾向等）。\n"
            "输出格式（必须严格按以下顺序，每行一项）：\n"
            "理论应用：...\n"
            "观察证据：...\n"
            "评价结论：...\n"
            "改进建议：...\n"
            "最后一行必须是：基于【选择的理论】该学生【类似这样的结论】。\n"
        ),
    }
    return (
        global_prompt
        + "\n\n"
        + function_map.get(function_key, "")
        + "\n禁止输出任何Markdown语法符号：不要使用 #、##、###、****、**、*、>、```、--- 等，只输出普通文本与换行。"
    )


def _sanitize_analysis_text(text: str) -> str:
    """
    Convert Markdown-ish analysis output into plain text for mentor display.
    """
    if not text:
        return ""
    # Remove fenced code blocks first
    text = re.sub(r"```[\\s\\S]*?```", "", text)
    # Remove heading markers
    text = re.sub(r"(?m)^\\s*#{1,6}\\s*", "", text)
    # Remove horizontal rules made of dashes/asterisks
    text = re.sub(r"(?m)^\\s*[-*_]{3,}\\s*$", "", text)
    # Remove bold/italic markers
    text = text.replace("****", "").replace("**", "").replace("*", "")
    # Remove leftover multiple spaces
    text = re.sub(r"[ \\t]{2,}", " ", text)
    # Trim excessive blank lines
    text = re.sub(r"\\n{3,}", "\\n\\n", text)
    return text.strip()


def _mentor_performance_bundle(user_id: str) -> dict[str, Any]:
    uid = _safe_str(user_id).strip()
    analytics = list_all_analytics_for_user(uid)
    raw_prof = get_profile(uid)
    profile_summary: dict[str, Any] = {}
    for k, v in raw_prof.items():
        if k == "persona_transcript":
            if isinstance(v, list):
                profile_summary["persona_transcript_turns"] = len(v)
            continue
        profile_summary[k] = v

    projects = list_projects(uid)
    projects_summary: list[dict[str, Any]] = []
    total_dialogues = 0
    for p in projects:
        if not isinstance(p, dict):
            continue
        dialogs = p.get("dialogues")
        dc = len(dialogs) if isinstance(dialogs, list) else 0
        total_dialogues += dc
        projects_summary.append(
            {
                "id": str(p.get("id") or ""),
                "name": str(p.get("name") or ""),
                "dialogue_count": dc,
                "updatedAt": p.get("updatedAt"),
                "createdAt": p.get("createdAt"),
            }
        )

    def _ms_day_key(ms: int) -> str:
        if ms <= 0:
            return ""
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")

    daily: Counter[str] = Counter()
    module_activity_days: dict[str, Counter[str]] = {k: Counter() for k in analytics}
    for mod, rows in analytics.items():
        for r in rows:
            ms = int(r.get("updated_at") or 0)
            d = _ms_day_key(ms)
            if d:
                daily[d] += 1
                module_activity_days[mod][d] += 1

    recent_access = list_audit_for_user(user_id=uid, limit=100)
    for a in recent_access:
        ms = int(a.get("ts") or 0)
        d = _ms_day_key(ms)
        if d:
            daily[d] += 1

    daily_sorted = [{"date": d, "events": int(daily[d])} for d in sorted(daily.keys())]

    def _avg_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for r in rows:
            m = r.get("metrics")
            if not isinstance(m, dict):
                continue
            for nk, nv in m.items():
                if isinstance(nv, bool):
                    continue
                if isinstance(nv, (int, float)):
                    sums[nk] = sums.get(nk, 0.0) + float(nv)
                    counts[nk] = counts.get(nk, 0) + 1
        return {k: round(sums[k] / counts[k], 4) for k in sums if counts.get(k, 0) > 0}

    metrics_avg_by_module = {mod: _avg_metrics(rows) for mod, rows in analytics.items()}
    module_counts = {mod: len(rows) for mod, rows in analytics.items()}
    module_daily_top = {
        m: [{"date": d, "events": int(c)} for d, c in module_activity_days[m].most_common(14)]
        for m in module_activity_days
    }
    chart: dict[str, Any] = {
        "module_row_counts": module_counts,
        "metrics_avg_by_module": metrics_avg_by_module,
        "daily_total_events": daily_sorted,
        "module_daily_top": module_daily_top,
    }

    return {
        "user_id": uid,
        "profile": profile_summary,
        "projects_summary": {
            "project_count": len(projects_summary),
            "dialogue_count_total": total_dialogues,
            "projects": projects_summary,
        },
        "analytics_by_module": analytics,
        "chart": chart,
        "recent_access_log": recent_access,
        "generated_at_ms": int(time.time() * 1000),
    }


def _parse_score_reference(text: str) -> tuple[int | None, str | None]:
    if not text:
        return None, None
    score = None
    ref = None
    m = _SCORE_RE.search(text)
    if m:
        try:
            v = int(m.group(1))
            if 1 <= v <= 15:
                score = v
        except Exception:
            score = None
    m2 = _REF_RE.search(text)
    if m2:
        ref = (m2.group(1) or "").strip()
    return score, ref

def _sse(data: str, *, event: str | None = None) -> str:
    if event:
        return f"event: {event}\ndata: {data}\n\n"
    return f"data: {data}\n\n"


@app.post("/ecm/auth/login")
def auth_login():
    """
    简单登录：如果用户不存在，则自动创建。
    Body: { "username": "...", "password": "...", "captcha": "...", "userType": "student|mentor|prompts" }
    """
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    captcha = (body.get("captcha") or "").strip()
    user_type = (body.get("userType") or body.get("user_type") or "").strip() or "student"
    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400
    expected = {"student": "123456", "mentor": "asdfgh", "prompts": "xcvbnm"}.get(user_type, "123456")
    if captcha != expected:
        return jsonify({"error": "invalid captcha"}), 403
    try:
        user = upsert_user(username, password)
    except ValueError as e:
        return jsonify({"error": str(e)}), 401
    # 不返回密码
    return jsonify({"id": user["id"], "username": user["username"]})


@app.post("/ecm/auth/register")
def auth_register():
    """
    简单注册：用户已存在则报错，不做自动创建。
    Body: { "username": "...", "password": "...", "captcha": "...", "userType": "student|mentor|prompts" }
    """
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    captcha = (body.get("captcha") or "").strip()
    user_type = (body.get("userType") or body.get("user_type") or "").strip() or "student"
    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400
    expected = {"student": "123456", "mentor": "asdfgh", "prompts": "xcvbnm"}.get(user_type, "123456")
    if captcha != expected:
        return jsonify({"error": "invalid captcha"}), 403
    try:
        user = create_user(username, password)
    except ValueError as e:
        msg = str(e) or "注册失败"
        if "已存在" in msg:
            return jsonify({"error": msg}), 409
        return jsonify({"error": msg}), 400
    return jsonify({"id": user["id"], "username": user["username"]})


def _require_admin():
    sec = (settings.ecm_admin_secret or "").strip()
    if not sec:
        return jsonify({"error": "Admin not configured (set ECM_ADMIN_SECRET)"}), 503
    got = (request.headers.get("X-ECM-Admin-Secret") or "").strip()
    if len(got) != len(sec) or not hmac.compare_digest(got.encode("utf-8"), sec.encode("utf-8")):
        return jsonify({"error": "Unauthorized"}), 401
    return None


@app.get("/ecm/admin/ping")
def admin_ping():
    err = _require_admin()
    if err:
        return err
    return jsonify({"ok": True})


@app.get("/ecm/admin/overview")
def admin_overview():
    err = _require_admin()
    if err:
        return err
    users = load_users()
    projects = load_projects()
    safe_users: list[dict[str, Any]] = []
    for u in users:
        if not isinstance(u, dict):
            continue
        safe_users.append({"id": str(u.get("id") or ""), "username": str(u.get("username") or "")})
    return jsonify(
        {
            "users_count": len(safe_users),
            "projects_count": len(projects) if isinstance(projects, list) else 0,
            "users": safe_users,
            "analytics_counts": analytics_table_counts(),
            "recent_audit": list_audit(limit=80, offset=0),
        }
    )


@app.get("/ecm/admin/audit")
def admin_audit_list():
    err = _require_admin()
    if err:
        return err
    try:
        lim = int(request.args.get("limit") or 100)
    except ValueError:
        lim = 100
    try:
        off = int(request.args.get("offset") or 0)
    except ValueError:
        off = 0
    return jsonify({"items": list_audit(limit=lim, offset=off)})


@app.get("/ecm/admin/projects")
def admin_projects_list():
    err = _require_admin()
    if err:
        return err
    projects = load_projects()
    out: list[dict[str, Any]] = []
    if isinstance(projects, list):
        for p in projects:
            if not isinstance(p, dict):
                continue
            ds = p.get("dialogues")
            dc = len(ds) if isinstance(ds, list) else 0
            out.append(
                {
                    "id": p.get("id"),
                    "userId": p.get("userId"),
                    "name": p.get("name"),
                    "createdAt": p.get("createdAt"),
                    "updatedAt": p.get("updatedAt"),
                    "dialogue_count": dc,
                }
            )
    return jsonify({"items": out})


@app.get("/ecm/admin/notes")
def admin_notes_summary():
    err = _require_admin()
    if err:
        return err
    n = load_notes()
    topic = str(n.get("topic") or "")
    tags = n.get("tags") if isinstance(n.get("tags"), list) else []
    quotes = n.get("quotes") if isinstance(n.get("quotes"), list) else []
    hooks = n.get("hooks") if isinstance(n.get("hooks"), list) else []
    return jsonify(
        {
            "topic_len": len(topic),
            "tags_count": len(tags),
            "quotes_count": len(quotes),
            "hooks_count": len(hooks),
            "topic_preview": topic[:800],
        }
    )


@app.get("/ecm/admin/analytics/<module>")
def admin_analytics_preview(module: str):
    err = _require_admin()
    if err:
        return err
    try:
        lim = int(request.args.get("limit") or 30)
    except ValueError:
        lim = 30
    return jsonify({"module": module, "items": list_recent_analytics_rows(module=module, limit=lim)})


@app.get("/ecm/mentor/student_performance_bundle")
def mentor_student_performance_bundle():
    user_id = _safe_str(request.args.get("userId") or request.args.get("user_id") or "").strip()
    if not user_id:
        return jsonify({"error": "userId is required"}), 400
    return jsonify(_mentor_performance_bundle(user_id))


@app.get("/ecm/mentor/student_performance_charts")
def mentor_student_performance_charts():
    """
    Matplotlib PNG figures + ordered timeline metadata (dialogue order, event sequence).
    """
    user_id = _safe_str(request.args.get("userId") or request.args.get("user_id") or "").strip()
    if not user_id:
        return jsonify({"error": "userId is required"}), 400
    analytics = list_all_analytics_for_user(user_id)
    try:
        from .mentor_perf_charts import build_timeline_events_payload, render_performance_figures_png

        timeline = build_timeline_events_payload(analytics)
        figures = render_performance_figures_png(analytics)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"timeline": timeline, "figures": figures})


@app.post("/ecm/mentor/student_behavior_analysis")
def mentor_student_behavior_analysis():
    if not settings.deepseek_api_key:
        return (
            jsonify({"error": "Missing DEEPSEEK_API_KEY. Create .env in ecm_backend and set it."}),
            500,
        )
    body = request.get_json(silent=True) or {}
    user_id = _safe_str(body.get("userId") or body.get("user_id") or "").strip()
    if not user_id:
        return jsonify({"error": "userId is required"}), 400
    bundle = _mentor_performance_bundle(user_id)
    system_prompt = load_prompt("mentor_behavior_theory.txt")

    # For DeepSeek: provide structured chart-ready time-series context (no PNGs).
    try:
        from .mentor_perf_charts import build_deepseek_charts_context

        analytics_for_charts = bundle.get("analytics_by_module") if isinstance(bundle.get("analytics_by_module"), dict) else {}
        charts_context = build_deepseek_charts_context(analytics_for_charts)
    except Exception:
        charts_context = {"error": "build_deepseek_charts_context failed"}

    deepseek_obj = {
        "profile": bundle.get("profile") or {},
        "projects_summary": bundle.get("projects_summary") or {},
        # Aggregated daily/module stats (already used in UI).
        "chart": bundle.get("chart") or {},
        # Chart-derived time-series context: ordered events + top metric trends.
        "charts_deepseek_context": charts_context,
        "recent_access_log": bundle.get("recent_access_log") or [],
    }

    payload = json.dumps(deepseek_obj, ensure_ascii=False)
    max_chars = 100_000
    truncated = len(payload) > max_chars
    if truncated:
        payload = payload[:max_chars] + "\n... [truncated for model context]"
    user_input = (
        "以下 JSON 包含学生在 ECM 中的跨模块表现摘要（可能已截断）。请按你的系统指令输出中文 Markdown 解读。\n"
        "重要：请务必把解读重点放在 charts_deepseek_context 这部分的“对话先后排序的时间序列图表数据”（模块推进、指标趋势、体量投入 proxy）。\n\n"
        + payload
    )
    try:
        resp = asyncio.run(
            call_deepseek(
                system_prompt=system_prompt,
                user_input=user_input,
                max_tokens=2800,
                temperature=0.25,
            )
        )
        analysis = extract_assistant_content(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"analysis": (analysis or "").strip(), "payload_truncated": truncated})


@app.post("/ecm/mentor/analyze")
def mentor_analyze():
    """
    Mentor: generate AI analysis for a specific function.
    Body:
      {
        functionKey: 'f1'|'f2'|'f3'|'f4'|'f5',
        userProfile?: {...},
        module1Definition?: string,
        noteText?: string,
        chats?: { f1?: [], f2?: [], f4?: [], f5?: [] }
      }
    """
    body = request.get_json(silent=True) or {}
    function_key = _safe_str(body.get("functionKey")).strip()
    if function_key not in ("f1", "f2", "f3", "f4", "f5"):
        return jsonify({"error": "functionKey must be one of f1/f2/f3/f4/f5"}), 400

    user_profile = body.get("userProfile") or {}
    module1_definition = _safe_str(body.get("module1Definition") or "")
    note_text = _safe_str(body.get("noteText") or "")
    chats_obj = body.get("chats") or {}
    conversation_id = _safe_str(body.get("conversation_id") or body.get("conversationId") or "").strip()

    history_raw = chats_obj.get(function_key) if isinstance(chats_obj, dict) else None
    history = _history_role_messages(history_raw)
    f1_db_metrics: dict[str, object] | None = None
    f2_db_metrics: dict[str, object] | None = None
    f3_db_metrics: dict[str, object] | None = None
    f3_db_cards: list[dict[str, object]] | None = None
    f4_db_metrics: dict[str, object] | None = None
    f5_db_metrics: dict[str, object] | None = None
    f4_db_report: str | None = None
    f5_db_review: str | None = None
    if function_key == "f1" and conversation_id:
        row = get_f1_analytics(conversation_id)
        if row:
            db_hist = row.get("history")
            if isinstance(db_hist, list) and db_hist:
                history_raw = db_hist
                history = _history_role_messages(db_hist)
            db_metrics = row.get("metrics")
            if isinstance(db_metrics, dict):
                f1_db_metrics = db_metrics
    if function_key == "f2" and conversation_id:
        row2 = get_f2_analytics(conversation_id)
        if row2:
            db_metrics2 = row2.get("metrics")
            if isinstance(db_metrics2, dict):
                f2_db_metrics = db_metrics2
            db_hist2 = row2.get("history")
            if isinstance(db_hist2, list) and db_hist2:
                history_raw = db_hist2
                history = _history_role_messages(db_hist2)
    if function_key == "f3" and conversation_id:
        row3 = get_f3_analytics(conversation_id)
        if row3:
            db_metrics3 = row3.get("metrics")
            if isinstance(db_metrics3, dict):
                f3_db_metrics = db_metrics3
            db_cards = row3.get("cards")
            if isinstance(db_cards, list):
                f3_db_cards = db_cards
            db_note = _safe_str(row3.get("note_text") or "")
            if db_note.strip():
                note_text = db_note
    if function_key == "f4" and conversation_id:
        row4 = get_f4_analytics(conversation_id)
        if row4:
            db_metrics4 = row4.get("metrics")
            if isinstance(db_metrics4, dict):
                f4_db_metrics = db_metrics4
            db_rep = row4.get("report_text")
            if isinstance(db_rep, str) and db_rep.strip():
                f4_db_report = db_rep
                # Also append into history for evidence consistency.
                history = history or []
                if not history:
                    history = [{"role": "assistant", "content": db_rep}]
    if function_key == "f5" and conversation_id:
        row5 = get_f5_analytics(conversation_id)
        if row5:
            db_metrics5 = row5.get("metrics")
            if isinstance(db_metrics5, dict):
                f5_db_metrics = db_metrics5
            db_rev = row5.get("ai_review_text")
            if isinstance(db_rev, str) and db_rev.strip():
                f5_db_review = db_rev
                history = history or []
                if not history:
                    history = [{"role": "assistant", "content": db_rev}]

    def _is_placeholder_like_text(t: str) -> bool:
        """
        Heuristic: treat prerequisite hints / default placeholders as "empty content"
        so mentor analysis won't be generated for functions that weren't really completed.
        """
        x = (t or "").strip()
        if not x:
            return True
        if x in ("（无）", "(无)", "（无内容）", "（无）（无）"):
            return True
        # Common UI placeholders / prerequisite messages.
        if re.match(r"^(请先|当前 Function|Function\\s*\\d+|如需继续|Function\\s*\\d+\\s*已完成|Function\\s*\\d+\\s*已记录)", x):
            return True
        # Too short often means it's not a real AI-generated section.
        if len(x) < 20:
            return True
        return False

    def _meaningful_history_len(hist: list[dict[str, str]]) -> int:
        if not hist:
            return 0
        parts: list[str] = []
        for m in hist:
            if not isinstance(m, dict):
                continue
            c = _safe_str(m.get("content") or "").strip()
            if not c:
                continue
            if _is_placeholder_like_text(c):
                continue
            parts.append(c)
        return len("".join(parts))

    def _is_confirm_only(t: str) -> bool:
        x = (t or "").strip()
        if not x:
            return False
        # Match common single-turn confirmations (students often type only these).
        if re.match(r"^(确认|是的|对|没错|好的|好|ok|OK|行|可以|收到|同意)$", x):
            return True
        return False

    def _first_non_confirm_user_excerpt(user_msgs: list[dict[str, str]]) -> str:
        for m in user_msgs:
            c = _safe_str(m.get("content") or "")
            if not c:
                continue
            if _is_confirm_only(c):
                continue
            if len(c.strip()) < 5:
                continue
            return c.strip()[:120]
        return ""

    # Strict rule: if the selected Function has no meaningful content, skip generating analysis.
    if function_key in ("f1", "f2", "f4", "f5"):
        min_len = {"f1": 30, "f2": 30, "f4": 60, "f5": 60}.get(function_key, 30)
        if len(history) == 0 or _meaningful_history_len(history) < min_len:
            return jsonify({"analysis": ""})
    if function_key == "f3":
        if not note_text.strip():
            return jsonify({"analysis": ""})
        # If it's only markers with "(无)/(无内容)", skip.
        cleaned = note_text
        cleaned = re.sub(r"\\[Step\\s*\\d+\\s*提炼\\]", "", cleaned)
        cleaned = cleaned.replace("（无）", "").replace("(无)", "")
        cleaned = re.sub(r"\\s+", "", cleaned).strip()
        if len(cleaned) < 20:
            return jsonify({"analysis": ""})

    # Metrics (especially for F2)
    additional_metrics: dict[str, object] = {
        "functionKey": function_key,
        "turnCount": len(history),
    }

    f2_scores: list[int] = []
    f2_step_count = None
    f2_submit_count = None
    f2_followup_count = None

    if function_key == "f2":
        # compute from raw history to preserve action/content
        raw_list = history_raw if isinstance(history_raw, list) else []
        for m in raw_list:
            if not isinstance(m, dict):
                continue
            role = _safe_str(m.get("role")).strip()
            content = _safe_str(m.get("content")).strip()
            action = _safe_str(m.get("action")).strip()
            if role == "assistant" and content:
                f2_scores.extend(_extract_scores(content))
            if role == "user":
                if action == "submit":
                    f2_submit_count = 0 if f2_submit_count is None else f2_submit_count
                    f2_submit_count += 1
                if action == "followup":
                    f2_followup_count = 0 if f2_followup_count is None else f2_followup_count
                    f2_followup_count += 1
        f2_step_count = f2_submit_count if f2_submit_count is not None else (len(f2_scores) if f2_scores else 0)
        additional_metrics["stepCount"] = f2_step_count
        additional_metrics["scoreCount"] = len(f2_scores)
        additional_metrics["scores"] = f2_scores[:50]
        additional_metrics["submitTurns"] = f2_submit_count
        additional_metrics["followupTurns"] = f2_followup_count

    if function_key == "f1":
        additional_metrics["assistantTurns"] = len([m for m in history if m.get("role") == "assistant"])
        if f1_db_metrics:
            additional_metrics["f1_metrics_from_db"] = f1_db_metrics
        # Student-feedback focus: whether student gave non-confirm modification/clarification after the "definition confirmation" prompt.
        f1_confirm_idx = None
        for i in range(len(history) - 1, -1, -1):
            m = history[i]
            if m.get("role") != "assistant":
                continue
            c = _safe_str(m.get("content") or "")
            if "这个定义准确吗" in c or "关键词准确吗" in c:
                f1_confirm_idx = i
                break
        user_after_confirm = []
        if f1_confirm_idx is not None:
            user_after_confirm = [m for m in history[f1_confirm_idx + 1 :] if m.get("role") == "user" and _safe_str(m.get("content") or "").strip()]
        # If student only replies "确认/是的/对" etc., treat as "no effective feedback".
        f1_student_feedback_provided = bool(_first_non_confirm_user_excerpt(user_after_confirm))
        additional_metrics["f1_student_feedback_provided"] = f1_student_feedback_provided
        additional_metrics["f1_student_feedback_excerpt"] = _first_non_confirm_user_excerpt(user_after_confirm)
        additional_metrics["f1_student_only_confirm_turns"] = len([m for m in user_after_confirm if _is_confirm_only(_safe_str(m.get("content") or ""))])
    if function_key == "f2":
        if f2_db_metrics:
            additional_metrics["f2_metrics_from_db"] = f2_db_metrics
        # Student-feedback focus: extra "followup" branch indicates more feedback depth than only "submit".
        additional_metrics["f2_student_branch_feedback_provided"] = (f2_followup_count or 0) > 0
    if function_key == "f3":
        if f3_db_metrics:
            additional_metrics["f3_metrics_from_db"] = f3_db_metrics
        if f3_db_cards is not None:
            additional_metrics["f3_cards"] = f3_db_cards[:200]
        # Student-feedback focus: edits/star/unstar indicate active feedback rather than passive acceptance.
        if isinstance(f3_db_metrics, dict):
            additional_metrics["f3_student_edit_feedback_provided"] = int(f3_db_metrics.get("user_edit_count") or 0) > 0
    if function_key == "f4":
        if f4_db_metrics:
            additional_metrics["f4_metrics_from_db"] = f4_db_metrics
        if f4_db_report:
            additional_metrics["f4_report_from_db"] = _safe_str(f4_db_report)
        # Student-feedback focus: after the final generated report, did the student provide any non-confirm modification request?
        f4_report_idx = None
        for i in range(len(history) - 1, -1, -1):
            m = history[i]
            if m.get("role") != "assistant":
                continue
            c = _safe_str(m.get("content") or "")
            if _is_placeholder_like_text(c):
                continue
            if ("道法术器势" in c) or re.search(r"道.*法.*术.*器.*势", c):
                f4_report_idx = i
                break
            if len(c) > 120:
                # fallback: long assistant content (likely the report)
                f4_report_idx = i
                break
        user_after_report = []
        if f4_report_idx is not None:
            user_after_report = [m for m in history[f4_report_idx + 1 :] if m.get("role") == "user" and _safe_str(m.get("content") or "").strip()]
        f4_student_feedback_provided = bool(_first_non_confirm_user_excerpt(user_after_report))
        additional_metrics["f4_student_feedback_provided"] = f4_student_feedback_provided
        additional_metrics["f4_student_feedback_excerpt"] = _first_non_confirm_user_excerpt(user_after_report)
        additional_metrics["f4_student_only_confirm_turns"] = len([m for m in user_after_report if _is_confirm_only(_safe_str(m.get("content") or ""))])
    if function_key == "f5":
        if f5_db_metrics:
            additional_metrics["f5_metrics_from_db"] = f5_db_metrics
        if f5_db_review:
            additional_metrics["f5_ai_review_from_db"] = _safe_str(f5_db_review)
        # Student-feedback focus: note edits/clicks reflect active feedback; passive acceptance means no feedback.
        if isinstance(f5_db_metrics, dict):
            note_edit_count = int(f5_db_metrics.get("note_edit_count") or 0)
            click_count = int(f5_db_metrics.get("click_count") or 0)
            new_count = int(f5_db_metrics.get("new_count") or 0)
            additional_metrics["f5_student_feedback_provided"] = (note_edit_count + click_count + new_count) > 0
            additional_metrics["f5_student_note_edit_provided"] = note_edit_count > 0
            additional_metrics["f5_student_click_or_new_provided"] = (click_count + new_count) > 0
    if function_key in ("f4", "f5"):
        additional_metrics["assistantTurns"] = len([m for m in history if m.get("role") == "assistant"])

    system_prompt = _analyze_function_system_prompt(function_key)

    user_input_obj = {
        "history": history,
        "user_profile": user_profile if isinstance(user_profile, dict) else {},
        "additional_metrics": additional_metrics,
    }
    # Only include the per-function content to avoid cross-function influence.
    if function_key == "f1":
        user_input_obj["module1Definition"] = module1_definition
    if function_key == "f3":
        user_input_obj["noteText"] = note_text

    user_input_obj["instruction"] = "Please produce the analysis strictly following the per-function requirements, and output plain text only."
    user_input = json.dumps(user_input_obj, ensure_ascii=False)

    try:
        resp = asyncio.run(call_deepseek(system_prompt=system_prompt, user_input=user_input, max_tokens=1100, temperature=0.2))
        analysis = extract_assistant_content(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"analysis": _sanitize_analysis_text(analysis)})


@app.post("/ecm/analytics/f1/upsert")
def f1_analytics_upsert():
    """
    Student-side F1 analytics persistence.
    Body:
      {
        conversation_id, user_id, project_id, dialogue_id,
        history: [{role, content, timestamp, ...}],
        metrics: {...}
      }
    """
    body = request.get_json(silent=True) or {}
    conversation_id = _safe_str(body.get("conversation_id") or body.get("conversationId") or "").strip()
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    user_id = _safe_str(body.get("user_id") or body.get("userId") or "").strip()
    project_id = _safe_str(body.get("project_id") or body.get("projectId") or "").strip()
    dialogue_id = _safe_str(body.get("dialogue_id") or body.get("dialogueId") or "").strip()
    history_raw = body.get("history")
    history = history_raw if isinstance(history_raw, list) else []
    metrics_raw = body.get("metrics")
    metrics = metrics_raw if isinstance(metrics_raw, dict) else {}
    updated_at = int(time.time() * 1000)
    try:
        upsert_f1_analytics(
            conversation_id=conversation_id,
            user_id=user_id,
            project_id=project_id,
            dialogue_id=dialogue_id,
            history=history,
            metrics=metrics,
            updated_at_ms=updated_at,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "updated_at": updated_at})


@app.post("/ecm/analytics/f2/upsert")
def f2_analytics_upsert():
    """
    Student-side F2 analytics persistence.
    Body:
      {
        conversation_id, user_id, project_id, dialogue_id,
        history: [{role, content, timestamp, action, parentId, depth, ...}],
        metrics: {...}
      }
    """
    body = request.get_json(silent=True) or {}
    conversation_id = _safe_str(body.get("conversation_id") or body.get("conversationId") or "").strip()
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    user_id = _safe_str(body.get("user_id") or body.get("userId") or "").strip()
    project_id = _safe_str(body.get("project_id") or body.get("projectId") or "").strip()
    dialogue_id = _safe_str(body.get("dialogue_id") or body.get("dialogueId") or "").strip()
    history_raw = body.get("history")
    history = history_raw if isinstance(history_raw, list) else []
    metrics_raw = body.get("metrics")
    metrics = metrics_raw if isinstance(metrics_raw, dict) else {}
    updated_at = int(time.time() * 1000)
    try:
        upsert_f2_analytics(
            conversation_id=conversation_id,
            user_id=user_id,
            project_id=project_id,
            dialogue_id=dialogue_id,
            history=history,
            metrics=metrics,
            updated_at_ms=updated_at,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "updated_at": updated_at})


def _simple_bloom_level(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["设计", "创新", "创造", "重构", "新方案", "create", "design"]):
        return "创造"
    if any(k in t for k in ["评价", "比较", "权衡", "优缺点", "评估", "justify"]):
        return "评价"
    if any(k in t for k in ["分析", "拆解", "因果", "结构", "模式", "analy"]):
        return "分析"
    if any(k in t for k in ["应用", "迁移", "使用", "实操", "练习", "apply"]):
        return "应用"
    if any(k in t for k in ["解释", "说明", "理解", "概念", "复述", "understand"]):
        return "理解"
    return "记忆"


@app.post("/ecm/analytics/f3/upsert")
def f3_analytics_upsert():
    """
    Student-side F3 analytics persistence.
    Body:
      {
        conversation_id, user_id, project_id, dialogue_id,
        note_text: string,
        metrics: {
          user_edit_count, avg_similarity, avg_update_depth,
          card_count, edited_card_count, edit_rate
        }
      }
    """
    body = request.get_json(silent=True) or {}
    conversation_id = _safe_str(body.get("conversation_id") or body.get("conversationId") or "").strip()
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    user_id = _safe_str(body.get("user_id") or body.get("userId") or "").strip()
    project_id = _safe_str(body.get("project_id") or body.get("projectId") or "").strip()
    dialogue_id = _safe_str(body.get("dialogue_id") or body.get("dialogueId") or "").strip()
    note_text = _safe_str(body.get("note_text") or body.get("noteText") or "")
    metrics_raw = body.get("metrics")
    metrics = metrics_raw if isinstance(metrics_raw, dict) else {}

    cards: list[dict[str, object]] = []
    parts = re.split(r"(?=\[Step\s*\d+\s*提炼\])", note_text)
    for idx, part in enumerate(parts):
        content = _safe_str(part).strip()
        if not content:
            continue
        step_m = re.search(r"\[Step\s*(\d+)\s*提炼\]", content)
        step_num = int(step_m.group(1)) if step_m else (idx + 1)
        cards.append(
            {
                "card_id": f"f3-step-{step_num}-{idx}",
                "conversation_id": conversation_id,
                "step": step_num,
                "content": content,
                "bloom_level": _simple_bloom_level(content),
                "is_edited": bool(metrics.get("user_edit_count", 0)),
                "edit_history": [],
                "is_starred": False,
            }
        )

    merged_metrics = {
        "user_edit_count": int(metrics.get("user_edit_count") or 0),
        "avg_similarity": float(metrics.get("avg_similarity") or 0),
        "avg_update_depth": float(metrics.get("avg_update_depth") or 0),
        "card_count": int(metrics.get("card_count") or len(cards)),
        "edited_card_count": int(metrics.get("edited_card_count") or 0),
        "edit_rate": float(metrics.get("edit_rate") or 0),
        "star_rate": float(metrics.get("star_rate") or 0),
        "send_rate": float(metrics.get("send_rate") or 0),
        "bloom_distribution": metrics.get("bloom_distribution") if isinstance(metrics.get("bloom_distribution"), dict) else {},
    }
    updated_at = int(time.time() * 1000)
    try:
        upsert_f3_analytics(
            conversation_id=conversation_id,
            user_id=user_id,
            project_id=project_id,
            dialogue_id=dialogue_id,
            note_text=note_text,
            cards=cards,
            metrics=merged_metrics,
            updated_at_ms=updated_at,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "updated_at": updated_at, "card_count": len(cards)})


def _sentiment_label_from_text(text: str) -> str:
    t = (text or "").lower()
    pos_words = ["积极", "正面", "鼓励", "建议", "可以", "会", "很棒", "优秀", "成长", "提升", "自信", "期待", "成功", "有效", "良好", "喜欢"]
    neg_words = ["消极", "负面", "担心", "困难", "失败", "无效", "不行", "问题", "不佳", "焦虑", "挫折", "挫败", "痛苦", "恐惧", "失败", "低效"]
    pos = sum(1 for w in pos_words if w in t)
    neg = sum(1 for w in neg_words if w in t)
    if pos > neg:
        return "积极"
    if neg > pos:
        return "消极"
    return "中性"


@app.post("/ecm/analytics/f4/upsert")
def f4_analytics_upsert():
    """
    Student-side F4 analytics persistence.
    Body:
      {
        conversation_id, user_id, project_id, dialogue_id,
        report_text: string,
        metrics: {...}
      }
    """
    body = request.get_json(silent=True) or {}
    conversation_id = _safe_str(body.get("conversation_id") or body.get("conversationId") or "").strip()
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    user_id = _safe_str(body.get("user_id") or body.get("userId") or "").strip()
    project_id = _safe_str(body.get("project_id") or body.get("projectId") or "").strip()
    dialogue_id = _safe_str(body.get("dialogue_id") or body.get("dialogueId") or "").strip()
    report_text = _safe_str(body.get("report_text") or body.get("reportText") or "")
    metrics_raw = body.get("metrics")
    metrics = metrics_raw if isinstance(metrics_raw, dict) else {}
    updated_at = int(time.time() * 1000)
    try:
        upsert_f4_analytics(
            conversation_id=conversation_id,
            user_id=user_id,
            project_id=project_id,
            dialogue_id=dialogue_id,
            report_text=report_text,
            metrics=metrics,
            updated_at_ms=updated_at,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "updated_at": updated_at})


@app.post("/ecm/analytics/f5/upsert")
def f5_analytics_upsert():
    """
    Student-side F5 analytics persistence.
    Body:
      {
        conversation_id, user_id, project_id, dialogue_id,
        ai_review_text: string,
        final_note_text: string,
        metrics: {...}
      }
    """
    body = request.get_json(silent=True) or {}
    conversation_id = _safe_str(body.get("conversation_id") or body.get("conversationId") or "").strip()
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    user_id = _safe_str(body.get("user_id") or body.get("userId") or "").strip()
    project_id = _safe_str(body.get("project_id") or body.get("projectId") or "").strip()
    dialogue_id = _safe_str(body.get("dialogue_id") or body.get("dialogueId") or "").strip()
    ai_review_text = _safe_str(body.get("ai_review_text") or body.get("aiReviewText") or "")
    final_note_text = _safe_str(body.get("final_note_text") or body.get("finalNoteText") or ai_review_text)
    metrics_raw = body.get("metrics")
    metrics = metrics_raw if isinstance(metrics_raw, dict) else {}

    metrics.setdefault("ai_sentiment_label", _sentiment_label_from_text(ai_review_text))
    updated_at = int(time.time() * 1000)
    try:
        upsert_f5_analytics(
            conversation_id=conversation_id,
            user_id=user_id,
            project_id=project_id,
            dialogue_id=dialogue_id,
            ai_review_text=ai_review_text,
            final_note_text=final_note_text,
            metrics=metrics,
            updated_at_ms=updated_at,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "updated_at": updated_at})


def _limit_str(s: str, *, max_chars: int) -> str:
    if not s:
        return ""
    s = str(s)
    if len(s) <= max_chars:
        return s
    return s[:max_chars]


def _sanitize_ooxml_plain_text(s: str) -> str:
    """
    Strip characters illegal in XML 1.0 text (except tab/LF/CR).
    Word shows '无法读取的内容' if document.xml contains invalid code points in w:t.
    """
    if not s:
        return ""
    out: list[str] = []
    for ch in s:
        o = ord(ch)
        if ch in "\t\n\r":
            out.append(ch)
            continue
        if o < 0x20:
            continue
        if o <= 0xD7FF:
            if 0xD800 <= o <= 0xDFFF:
                continue
            out.append(ch)
            continue
        if 0xE000 <= o <= 0xFFFD:
            out.append(ch)
            continue
        if 0x10000 <= o <= 0x10FFFF:
            out.append(ch)
    return "".join(out)


def _register_ooxml_prefixes_for_serialization(xml_bytes: bytes, *, scan: int = 20000) -> None:
    """
    xml.etree.ElementTree serializes unknown namespaces as ns0/ns1; Word often treats that as corrupt OOXML.
    Register xmlns:prefix declarations from the document prolog so output keeps w:, w14:, r:, etc.
    """
    chunk = xml_bytes[:scan].decode("utf-8", "ignore")
    for m in re.finditer(r'xmlns:([A-Za-z_][A-Za-z0-9_.-]*)="([^"]+)"', chunk):
        pfx, uri = m.group(1), m.group(2)
        if not pfx or not uri:
            continue
        try:
            ET.register_namespace(pfx, uri)
        except ValueError:
            pass


def _messages_to_transcript(history_raw: object) -> str:
    """
    Turn stored chat messages into a compact plain-text transcript for exporting.
    """
    msgs = history_raw if isinstance(history_raw, list) else []
    lines: list[str] = []
    # Export should include the whole Function interaction (not only the tail),
    # then we apply per-function character caps afterwards.
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = _safe_str(m.get("role")).strip()
        content = _safe_str(m.get("content")).strip()
        if not role or not content:
            continue
        lines.append(f"{role}：{content}")
    return "\n".join(lines).strip()


def _normalize_student_markdown(md: str) -> str:
    """
    Student Function 4/5 outputs are rendered with ReactMarkdown.
    Some model generations collapse newlines and/or use headings like '###📝Title'
    (missing the required space after '#'), which breaks Markdown block parsing.
    Normalize by:
    - ensure '###' starts on its own line
    - ensure headings have a space after hash marks: '### Title'
    - ensure bold section markers start on new lines
    - if Mermaid code fence is missing but 'graph LR/TD' exists, wrap it.
    """
    t = _safe_str(md)
    if not t:
        return ""

    # 1) Put headings on their own line when collapsed.
    t = re.sub(r"(?<!\n)###", "\n###", t)
    # 2) Ensure space after heading hashes at line start.
    t = re.sub(r"(?m)^(#{1,6})([^\s#])", r"\1 \2", t)
    # 3) Ensure bold numbered sections start on new line (best-effort).
    t = re.sub(r"(?<!\n)(\*\*[1-5]\.\s*)", r"\n\1", t)

    # 4) Mermaid fence auto-wrap (best-effort).
    # Model output sometimes collapses: 'mermaidgraphLR' / 'graphLR' without spaces/newlines.
    # Normalize common variants first, then wrap the first detected mermaid 'graph ...' block.
    t = re.sub(r"\bmermaid\s*graph\s*(LR|TD)\b", r"graph \1", t)
    t = re.sub(r"\bmermaidgraph\s*(LR|TD)\b", r"graph \1", t, flags=re.I)
    t = re.sub(r"\bgraph\s*(LR|TD)\b", r"graph \1", t)

    if "```mermaid" not in t:
        if re.search(r"\bgraph\s+(LR|TD)\b", t):
            # Wrap only the first mermaid-like graph block; stop at next '###' or end.
            t = re.sub(
                r"(?ms)^(graph\s+(?:LR|TD)\b[\s\S]*?)(?=^###|\Z)",
                lambda m: f"```mermaid\n{(m.group(1) or '').strip()}\n```",
                t,
                count=1,
            )

    # 5) Cleanup excessive blank lines introduced by normalization.
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _export_build_transcripts_and_fallbacks(body: dict) -> tuple[str, str, str, str, str, str, str, dict[str, dict[str, str]]]:
    """
    Shared: transcripts + fallback per-function {natural, bullets} when AI is off or fails.
    """
    project_name = _safe_str(body.get("projectName") or body.get("project_name") or "ECM探索导师").strip()
    dialogue_name = _safe_str(body.get("dialogueName") or body.get("dialogue_name") or "对话").strip()
    chats_obj = body.get("chats") or {}
    note_text = _safe_str(body.get("noteText") or "")
    module1_definition = _safe_str(body.get("module1Definition") or "")

    # Keep generous caps so DeepSeek can summarize from complete interaction,
    # while still staying within context length.
    f1_transcript = _limit_str(_messages_to_transcript(chats_obj.get("f1")), max_chars=20000)
    f2_transcript = _limit_str(_messages_to_transcript(chats_obj.get("f2")), max_chars=25000)
    f4_transcript = _limit_str(_messages_to_transcript(chats_obj.get("f4")), max_chars=25000)
    f5_transcript = _limit_str(_messages_to_transcript(chats_obj.get("f5")), max_chars=25000)
    f3_text = _limit_str(note_text, max_chars=30000)

    def to_bullets(text: str, *, max_lines: int = 8) -> str:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln and ln.strip()]
        if not lines:
            return ""
        return "\n".join("• " + ln for ln in lines[:max_lines])

    fallbacks: dict[str, dict[str, str]] = {
        "f1": {"natural": "", "bullets": to_bullets(f1_transcript)},
        "f2": {"natural": "", "bullets": to_bullets(f2_transcript)},
        "f3": {"natural": "", "bullets": to_bullets(f3_text)},
        "f4": {"natural": "", "bullets": to_bullets(f4_transcript)},
        "f5": {"natural": "", "bullets": to_bullets(f5_transcript)},
    }
    return (
        project_name,
        dialogue_name,
        module1_definition,
        f1_transcript,
        f2_transcript,
        f3_text,
        f4_transcript,
        f5_transcript,
        fallbacks,
    )


def _export_build_sections(body: dict) -> tuple[dict[str, dict[str, str]], str, str]:
    """
    Same DeepSeek pipeline as export_txt / export_word: per-function {natural, bullets} + fallbacks.
    """
    (
        project_name,
        dialogue_name,
        module1_definition,
        f1_transcript,
        f2_transcript,
        f3_text,
        f4_transcript,
        f5_transcript,
        sections,
    ) = _export_build_transcripts_and_fallbacks(body)

    if settings.deepseek_api_key:
        try:
            sys_prompt = (
                "你是「对话导出整理助手」。将学生在 ECM AI Studio 各 Function 的原始记录整理为「自然语言综述」与「要点列表」。\n"
                "硬性要求：\n"
                "1) 仅输出 JSON（不要任何解释、Markdown 代码块或前后缀）。\n"
                "2) JSON 必须包含键：f1,f2,f3,f4,f5。\n"
                "3) 每个键的值必须是一个对象，包含两个字符串字段：\n"
                '   - "natural"：必须输出 ""（本次导出仅使用要点列表）。\n'
                '   - "bullets"：每行以 "• " 开头，换行分隔；禁止 #、**、```、--- 等 Markdown；无内容则 ""。\n'
                "4) f1-f2-f4-f5 对应各自对话 transcript；f3 仅依据 noteText（Function 3 笔记）。\n"
                "5) 输出要点的写法规则：\n"
                "   - 必须突出双方互动后的学习成果/结论变化/转折点（例如：确认后的定义落地、探索步进后的范围收敛、追问后的报告修订点、最终笔记的结构化产出）。\n"
                "   - 语言简洁客观：只描述已形成的结论，不编造未出现的内容；避免主观评价（如“很好/优秀/震撼/明显更强”等）。\n"
                "   - 禁止逐句复述原文或大段复制：每条要点必须是压缩后的结论性表达。\n"
                "   - 字数控制：把所有模块 bullets 的文字部分相加，整体控制在 500-800 字（不含换行符）。\n"
                "   - 粗略分配建议：f1 120-160，f2 130-180，f3 70-120，f4 120-170，f5 60-120（允许有少量偏差，但总和仍需落在 500-800）。\n"
                "   - 每条 bullet 建议不超过 35 字。\n"
            )
            user_input_obj = {
                "module1Definition": module1_definition,
                "f1": f1_transcript,
                "f2": f2_transcript,
                "f3": f3_text,
                "f4": f4_transcript,
                "f5": f5_transcript,
            }
            user_input = json.dumps(user_input_obj, ensure_ascii=False)
            resp = asyncio.run(
                call_deepseek(
                    system_prompt=sys_prompt,
                    user_input=user_input,
                    max_tokens=1200,
                    temperature=0.2,
                )
            )
            raw = extract_assistant_content(resp).strip()
            parsed = _extract_json_object(raw) or {}

            def clean_natural(s: object) -> str:
                t = _safe_str(s).strip()
                t = re.sub(r"```[\s\S]*?```", "", t)
                t = t.replace("****", "").replace("**", "").replace("*", "")
                t = re.sub(r"(?m)^\s*#{1,6}\s*", "", t)
                return t.strip()

            def clean_bullets(s: object) -> str:
                t = _safe_str(s).strip()
                t = re.sub(r"```[\s\S]*?```", "", t)
                t = t.replace("****", "").replace("**", "").replace("*", "")
                t = re.sub(r"(?m)^\s*#{1,6}\s*", "", t)
                t = t.replace("---", "")
                return t.strip()

            for key in ("f1", "f2", "f3", "f4", "f5"):
                val = parsed.get(key)
                if isinstance(val, dict):
                    sections[key] = {
                        # This export mode is bullet-only; force natural to empty.
                        "natural": "",
                        "bullets": clean_bullets(val.get("bullets")),
                    }
                elif isinstance(val, str):
                    sections[key] = {"natural": "", "bullets": clean_bullets(val)}
        except Exception:
            pass

    return sections, project_name, dialogue_name


@app.post("/ecm/student/export_word")
def student_export_word():
    """
    Student: export Function 1-5 to Word (.docx) using export_template.docx.
    Same DeepSeek sections as export_txt; fills table cells (natural paragraph + 「要点」+ bullets).
    """
    body = request.get_json(silent=True) or {}
    # Prefer server-side stored dialogue state (full transcript),
    # because frontend refs/state can be incomplete after reload.
    try:
        user_id = _safe_str(body.get("userId") or body.get("user_id") or "").strip()
        project_id = _safe_str(body.get("projectId") or body.get("project_id") or "").strip()
        dialogue_id = _safe_str(body.get("dialogueId") or body.get("dialogue_id") or "").strip()
        if user_id and project_id and dialogue_id:
            d = load_dialogue(user_id, project_id, dialogue_id)
            st = d.get("state") if isinstance(d, dict) else None
            if isinstance(st, dict):
                # Merge into body so _export_build_sections uses the full data.
                if isinstance(st.get("chats"), dict):
                    body["chats"] = st.get("chats") or {}
                if isinstance(st.get("noteText"), str):
                    body["noteText"] = st.get("noteText")
                if isinstance(st.get("module1Definition"), str):
                    body["module1Definition"] = st.get("module1Definition")
    except Exception:
        # Export should never fail due to this best-effort merge.
        pass

    try:
        sections, _, _ = _export_build_sections(body)

        def bullets_to_items(bullets_text: str) -> list[str]:
            items: list[str] = []
            for ln in (bullets_text or "").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                ln = ln.lstrip("•").strip()
                if ln.startswith("- "):
                    ln = ln[2:].strip()
                if ln.startswith("* "):
                    ln = ln[2:].strip()
                items.append(ln)
            return items

        def section_to_cell_lines(sec: dict[str, str]) -> list[str]:
            nat = (sec.get("natural") or "").strip()
            nat_one = re.sub(r"\s+", " ", nat.replace("\r", " ").replace("\n", " ")).strip()
            if nat_one:
                # Natural language should be plain text without the "【自然语言】" prefix.
                line0 = nat_one
            else:
                line0 = "（无内容）"
            raw_bul = (sec.get("bullets") or "").strip()
            items = bullets_to_items(raw_bul)
            out: list[str] = [line0, "【要点】"]
            if not items:
                out.append("（无内容）")
            else:
                for it in items:
                    out.append(f"• {it}" if it and not str(it).startswith("•") else str(it))
            return out

        f1_lines = section_to_cell_lines(sections.get("f1") or {})
        f2_lines = section_to_cell_lines(sections.get("f2") or {})
        f3_lines = section_to_cell_lines(sections.get("f3") or {})
        f4_lines = section_to_cell_lines(sections.get("f4") or {})
        f5_lines = section_to_cell_lines(sections.get("f5") or {})

        tpl_path = os.path.join(os.path.dirname(__file__), "templates", "export_template.docx")
        if not os.path.exists(tpl_path):
            raise FileNotFoundError(f"Template not found: {tpl_path}")

        W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        NS = {"w": W_NS}

        with zipfile.ZipFile(tpl_path, "r") as zin:
            doc_xml = zin.read("word/document.xml")
            _register_ooxml_prefixes_for_serialization(doc_xml)
            root = ET.fromstring(doc_xml)
            tbls = root.findall(".//w:tbl", NS)
            if not tbls:
                raise ValueError("Template has no table (w:tbl) in word/document.xml")
            tbl = tbls[0]
            tr_list = tbl.findall(".//w:tr", NS)
            fill_map = {
                "f1": (1, 0, f1_lines),
                "f2": (3, 0, f2_lines),
                "f3": (3, 1, f3_lines),
                "f4": (5, 0, f4_lines),
                "f5": (5, 1, f5_lines),
            }
            for _key, (ri, ci, line_items) in fill_map.items():
                if ri >= len(tr_list):
                    continue
                tr = tr_list[ri]
                tcs = tr.findall("./w:tc", NS)
                if ci >= len(tcs):
                    continue
                tc = tcs[ci]

                ps = tc.findall("./w:p", NS)
                if not ps:
                    for line in line_items:
                        p = ET.SubElement(tc, f"{{{W_NS}}}p")
                        r = ET.SubElement(p, f"{{{W_NS}}}r")
                        t = ET.SubElement(r, f"{{{W_NS}}}t")
                        t.text = _sanitize_ooxml_plain_text(str(line))
                    continue

                def set_paragraph_text_by_creating_run(p_el: ET.Element, text: str) -> None:
                    ppr_tag = f"{{{W_NS}}}pPr"
                    for ch in list(p_el):
                        if ch.tag != ppr_tag:
                            p_el.remove(ch)
                    r = ET.SubElement(p_el, f"{{{W_NS}}}r")
                    t = ET.SubElement(r, f"{{{W_NS}}}t")
                    t.text = _sanitize_ooxml_plain_text(text or "")

                for i in range(len(ps)):
                    p_el = ps[i]
                    txt = str(line_items[i]) if i < len(line_items) and line_items[i] is not None else ""
                    set_paragraph_text_by_creating_run(p_el, txt)

                if len(line_items) > len(ps):
                    import copy

                    proto = ps[-1]
                    for i in range(len(ps), len(line_items)):
                        p_clone: ET.Element = copy.deepcopy(proto)
                        set_paragraph_text_by_creating_run(p_clone, str(line_items[i]))
                        tc.append(p_clone)

            new_doc_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)

            mem = io.BytesIO()
            with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for info in zin.infolist():
                    name = info.filename
                    if name == "word/document.xml":
                        zout.writestr(name, new_doc_xml)
                    else:
                        zout.writestr(name, zin.read(name))

            doc_bytes = mem.getvalue()

        doc_b64 = base64.b64encode(doc_bytes).decode("ascii")
        return jsonify({"filename": "ECM_export.docx", "base64": doc_b64})
    except Exception as e:
        return jsonify({"error": str(e), "detail": "export_word_failed"}), 500


@app.post("/ecm/student/export_txt")
def student_export_txt():
    """
    Student: export Function 1-5 as a UTF-8 .txt file.
    DeepSeek produces per-function natural language + bullet points; fallback uses raw bullet lines if API missing/fails.
    Response: JSON { filename, base64 } (UTF-8 text encoded as base64) for stable download in browser.
    """
    body = request.get_json(silent=True) or {}
    # Best-effort merge from stored dialogue state for full export.
    try:
        user_id = _safe_str(body.get("userId") or body.get("user_id") or "").strip()
        project_id = _safe_str(body.get("projectId") or body.get("project_id") or "").strip()
        dialogue_id = _safe_str(body.get("dialogueId") or body.get("dialogue_id") or "").strip()
        if user_id and project_id and dialogue_id:
            d = load_dialogue(user_id, project_id, dialogue_id)
            st = d.get("state") if isinstance(d, dict) else None
            if isinstance(st, dict):
                if isinstance(st.get("chats"), dict):
                    body["chats"] = st.get("chats") or {}
                if isinstance(st.get("noteText"), str):
                    body["noteText"] = st.get("noteText")
                if isinstance(st.get("module1Definition"), str):
                    body["module1Definition"] = st.get("module1Definition")
    except Exception:
        pass
    try:
        sections, project_name, dialogue_name = _export_build_sections(body)

        labels = {
            "f1": "Function 1 — 问题定义",
            "f2": "Function 2 — 深度探索",
            "f3": "Function 3 — 笔记/提炼",
            "f4": "Function 4 — 洞察与结构",
            "f5": "Function 5 — 元认知与循环",
        }
        from datetime import datetime

        header_lines = [
            "ECM探索导师 — 对话导出（TXT）",
            f"项目：{project_name}",
            f"对话：{dialogue_name}",
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]
        body_lines: list[str] = []
        for key in ("f1", "f2", "f3", "f4", "f5"):
            sec = sections.get(key) or {"natural": "", "bullets": ""}
            nat = (sec.get("natural") or "").strip()
            bul = (sec.get("bullets") or "").strip()
            body_lines.append("=" * 20 + " " + labels[key] + " " + "=" * 20)
            body_lines.append("【自然语言】")
            body_lines.append(nat if nat else "（无内容）")
            body_lines.append("")
            body_lines.append("【要点】")
            body_lines.append(bul if bul else "（无内容）")
            body_lines.append("")

        txt = "\n".join(header_lines + body_lines)
        # UTF-8 BOM helps Windows Notepad recognize encoding.
        txt_bytes = b"\xef\xbb\xbf" + txt.encode("utf-8")
        txt_b64 = base64.b64encode(txt_bytes).decode("ascii")
        safe_project = re.sub(r"[\\/:*?\"<>|]", "_", project_name)[:60]
        safe_dialogue = re.sub(r"[\\/:*?\"<>|]", "_", dialogue_name)[:60]
        safe_project = re.sub(r"[^\x00-\x7F]", "_", safe_project)
        safe_dialogue = re.sub(r"[^\x00-\x7F]", "_", safe_dialogue)
        # Suggested download name (ASCII); browser may still show user-friendly name from UI.
        filename = f"{safe_project}_{safe_dialogue}_ECM_export.txt"
        return jsonify({"filename": filename, "base64": txt_b64})
    except Exception as e:
        return jsonify({"error": str(e), "detail": "export_txt_failed"}), 500


@app.get("/ecm/projects/list")
def projects_list():
    user_id = (request.args.get("userId") or "").strip()
    if not user_id:
        return jsonify({"error": "userId is required"}), 400
    items = [
        {
            "id": p["id"],
            "name": p.get("name") or "未命名项目",
            "updatedAt": p.get("updatedAt"),
        }
        for p in list_projects(user_id)
    ]
    # 按更新时间倒序
    items.sort(key=lambda x: x.get("updatedAt") or 0, reverse=True)
    return jsonify(items)


@app.get("/ecm/users")
def users_list():
    """
    导师/管理端：查看所有注册用户（学生）。
    """
    users = load_users()
    return jsonify(
        [
            {
                "id": u.get("id"),
                "username": u.get("username") or "",
            }
            for u in users
            if u.get("id")
        ]
    )


@app.post("/ecm/projects/save")
def projects_save():
    body = request.get_json(silent=True) or {}
    user_id = (body.get("userId") or "").strip()
    project_id = (body.get("projectId") or "").strip() or None
    name = (body.get("name") or "").strip()
    state = body.get("state") or {}

    if not user_id:
        return jsonify({"error": "userId is required"}), 400
    if not isinstance(state, dict):
        return jsonify({"error": "state must be an object"}), 400

    proj = save_project(user_id=user_id, project_id=project_id, name=name, state=state)
    # first dialogue id (for new schema)
    first_dialogue_id = ""
    if isinstance(proj.get("dialogues"), list) and proj.get("dialogues"):
        d0 = (proj.get("dialogues") or [None])[0] or {}
        if isinstance(d0, dict):
            first_dialogue_id = str(d0.get("id") or "")
    return jsonify(
        {
            "id": proj["id"],
            "name": proj.get("name") or "未命名项目",
            "updatedAt": proj.get("updatedAt"),
            "dialogueId": first_dialogue_id,
        }
    )


@app.get("/ecm/projects/load")
def projects_load():
    user_id = (request.args.get("userId") or "").strip()
    project_id = (request.args.get("projectId") or "").strip()
    if not user_id or not project_id:
        return jsonify({"error": "userId and projectId are required"}), 400
    proj = load_project(user_id, project_id)
    if not proj:
        return jsonify({"error": "project not found"}), 404
    return jsonify(
        {
            "id": proj["id"],
            "name": proj.get("name") or "未命名项目",
            # backward compat: return first dialogue state if present
            "state": ((proj.get("dialogues") or [{}])[0] or {}).get("state") if isinstance(proj.get("dialogues"), list) else {},
        }
    )


@app.get("/ecm/dialogues/list")
def dialogues_list():
    user_id = (request.args.get("userId") or "").strip()
    project_id = (request.args.get("projectId") or "").strip()
    if not user_id or not project_id:
        return jsonify({"error": "userId and projectId are required"}), 400
    return jsonify(list_dialogues(user_id, project_id))


@app.post("/ecm/dialogues/create")
def dialogues_create():
    body = request.get_json(silent=True) or {}
    user_id = (body.get("userId") or "").strip()
    project_id = (body.get("projectId") or "").strip()
    name = (body.get("name") or "").strip()
    if not user_id or not project_id:
        return jsonify({"error": "userId and projectId are required"}), 400
    d = create_dialogue(user_id=user_id, project_id=project_id, name=name or "未命名对话")
    if not d:
        return jsonify({"error": "project not found"}), 404
    return jsonify({"id": d.get("id"), "name": d.get("name") or "未命名对话", "updatedAt": d.get("updatedAt")})


@app.get("/ecm/profile")
def profile_get():
    """Get current user profile for personalization."""
    user_id = (request.args.get("userId") or "").strip()
    if not user_id:
        return jsonify({"error": "userId is required"}), 400
    profile = get_profile(user_id)
    return jsonify({"profile": profile})


@app.post("/ecm/profile")
def profile_save():
    """Save user profile (age, stage, major, interests, hobbies)."""
    body = request.get_json(silent=True) or {}
    user_id = (body.get("userId") or "").strip()
    profile = body.get("profile") or {}
    if not user_id:
        return jsonify({"error": "userId is required"}), 400
    if not isinstance(profile, dict):
        return jsonify({"error": "profile must be an object"}), 400
    saved = save_profile(user_id, profile)
    return jsonify({"profile": saved})


@app.post("/ecm/persona/next_stream")
def persona_next_stream():
    """
    Persona Builder streaming endpoint.
    Body: { "userId": "...", "history": [{"role":"user|assistant","content":"..."}], "user_input": optional }
    SSE: data=<delta>, event: final data=<json>
    """
    if not settings.deepseek_api_key:
        return jsonify({"error": "Missing DEEPSEEK_API_KEY. Create .env in ecm_backend and set it."}), 500

    body = request.get_json(silent=True) or {}
    user_id = (body.get("userId") or body.get("user_id") or "").strip()
    history = body.get("history") or []
    user_input = (body.get("user_input") or body.get("userInput") or "").strip()

    if not user_id:
        return jsonify({"error": "userId is required"}), 400
    if not isinstance(history, list):
        return jsonify({"error": "history must be an array"}), 400

    # Count user turns (answers) to enforce 3–5 rounds.
    user_turns = 0
    for m in history:
        if isinstance(m, dict) and str(m.get("role") or "").strip() == "user" and str(m.get("content") or "").strip():
            user_turns += 1

    # Build a compact dialogue context.
    msgs: list[str] = []
    for m in history[-10:]:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip()
        content = str(m.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            msgs.append(f"{role}: {content}")
    if user_input:
        msgs.append(f"user: {user_input}")
    convo = "\n".join(msgs).strip()

    system_prompt = _persona_system_prompt(user_id)
    if user_turns < 3:
        round_rule = (
            f"当前用户已回答轮数：{user_turns}。\n"
            "你必须继续提问，禁止输出【Final Persona】。\n"
        )
    elif user_turns >= 5:
        round_rule = (
            f"当前用户已回答轮数：{user_turns}。\n"
            "你必须立刻输出【Final Persona】并收口，不要再追问。\n"
        )
    else:
        round_rule = (
            f"当前用户已回答轮数：{user_turns}。\n"
            "你可以在本轮或下一轮输出【Final Persona】（总轮数上限为 5）。\n"
        )
    model_user_input = (
        "请根据下面的对话继续 Persona Builder。\n"
        + round_rule
        + "\n"
        "最近对话：\n"
        + (convo or "（暂无）")
    )

    def gen():
        try:
            parts: list[str] = []
            for piece in stream_deepseek(system_prompt=system_prompt, user_input=model_user_input):
                parts.append(piece)
                yield _sse(piece)
            assistant_text = "".join(parts).strip()
        except Exception as e:
            assistant_text = str(e)
            yield _sse(assistant_text)

        done = "【Final Persona】" in assistant_text
        extracted = _extract_final_persona(assistant_text) if done else {"core_motivation": "", "end_goal": "", "learning_habits": "", "persona_summary": ""}

        yield _sse(
            json.dumps(
                {
                    "assistant": assistant_text,
                    "done": done,
                    "extracted": extracted,
                },
                ensure_ascii=False,
            ),
            event="final",
        )

    return Response(stream_with_context(gen()), mimetype="text/event-stream")


@app.get("/ecm/dialogues/load")
def dialogues_load():
    user_id = (request.args.get("userId") or "").strip()
    project_id = (request.args.get("projectId") or "").strip()
    dialogue_id = (request.args.get("dialogueId") or "").strip()
    if not user_id or not project_id or not dialogue_id:
        return jsonify({"error": "userId, projectId and dialogueId are required"}), 400
    p = load_project(user_id, project_id)
    if not p:
        return jsonify({"error": "project not found"}), 404
    d = load_dialogue(user_id, project_id, dialogue_id)
    if not d:
        return jsonify({"error": "dialogue not found"}), 404
    return jsonify(
        {
            "projectId": p.get("id"),
            "projectName": p.get("name") or "未命名项目",
            "id": d.get("id"),
            "name": d.get("name") or "未命名对话",
            "state": d.get("state") or {},
        }
    )


@app.post("/ecm/dialogues/save")
def dialogues_save():
    body = request.get_json(silent=True) or {}
    user_id = (body.get("userId") or "").strip()
    project_id = (body.get("projectId") or "").strip()
    dialogue_id = (body.get("dialogueId") or "").strip() or None
    name = (body.get("name") or "").strip()
    state = body.get("state") or {}
    if not user_id or not project_id:
        return jsonify({"error": "userId and projectId are required"}), 400
    if not isinstance(state, dict):
        return jsonify({"error": "state must be an object"}), 400
    d = save_dialogue(user_id=user_id, project_id=project_id, dialogue_id=dialogue_id, name=name, state=state)
    if not d:
        return jsonify({"error": "project not found"}), 404
    return jsonify({"id": d.get("id"), "name": d.get("name") or "未命名对话", "updatedAt": d.get("updatedAt")})


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.post("/ecm/run")
def ecm_run():
    if not settings.deepseek_api_key:
        return jsonify({"error": "Missing DEEPSEEK_API_KEY. Create .env in ecm_backend and set it."}), 500

    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    topic = body.get("topic")
    topic = None if topic is None else str(topic).strip()

    if not question:
        return jsonify({"error": "question is required"}), 400

    try:
        result = asyncio.run(run_ecm(topic, question))
        return jsonify(result)
    except Exception as e:  # MVP: keep simple
        return jsonify({"error": str(e)}), 500


@app.get("/ecm/prompts")
def get_prompts():
    """
    返回 6 个核心 prompt txt 的当前内容，供前端管理界面编辑。
    """
    base = _settings_for_prompts.prompts_dir

    def _read(name: str) -> str:
        path = os.path.join(base, name)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    return jsonify(
        {
            "module0_": _read("module0_.txt"),
            "module1_steps": _read("module1_steps.txt"),
            "module2_steps": _read("module2_steps.txt"),
            "module3_Summary": _read("module3_Summary.txt"),
            "module4_summary": _read("module4_summary.txt"),
            "module5_inspiration": _read("module5_inspiration.txt"),
        }
    )


@app.get("/ecm/prompts/module1")
def get_module1_steps():
    """
    导师端：将 module1_steps.txt 按“全局 + Step 列表”形式返回，便于动态增减步骤。
    """
    raw = load_prompt("module1_steps.txt")

    def _split(text: str) -> tuple[str, list[str]]:
        lines = text.splitlines()
        steps: list[list[str]] = []
        global_lines: list[str] = []
        cur: list[str] | None = None
        for ln in lines:
            if ln.strip().startswith("## Step "):
                cur = [ln]
                steps.append(cur)
                continue
            if cur is None:
                global_lines.append(ln)
            else:
                cur.append(ln)
        global_text = "\n".join(global_lines).strip()
        step_texts = ["\n".join(s).strip() for s in steps if "\n".join(s).strip()]
        return global_text, step_texts

    g, steps = _split(raw)
    return jsonify({"global": g, "steps": steps})


@app.post("/ecm/prompts/module1/save")
def save_module1_steps():
    """
    导师端：保存 module1_steps.txt（全局 + steps），并在首次保存时备份 defaults。
    Body: { "global": "...", "steps": ["...", "..."] }
    """
    body = request.get_json(silent=True) or {}
    global_text = body.get("global")
    steps = body.get("steps")
    if not isinstance(global_text, str):
        return jsonify({"error": "global must be string"}), 400
    if not isinstance(steps, list) or not all(isinstance(x, str) for x in steps):
        return jsonify({"error": "steps must be string array"}), 400
    steps = [s.strip() for s in steps if str(s).strip()]
    if len(steps) < 5:
        return jsonify({"error": "steps must have at least 5 items"}), 400

    content = (global_text.strip() + "\n\n" + "\n\n".join(steps).strip() + "\n")

    base = _settings_for_prompts.prompts_dir
    os.makedirs(base, exist_ok=True)
    filename = "module1_steps.txt"
    path = os.path.join(base, filename)
    defaults_dir = os.path.join(base, "defaults")
    os.makedirs(defaults_dir, exist_ok=True)
    backup_path = os.path.join(defaults_dir, filename)
    if os.path.isfile(path) and not os.path.isfile(backup_path):
        try:
            with open(path, "r", encoding="utf-8") as f_src, open(backup_path, "w", encoding="utf-8") as f_dst:
                f_dst.write(f_src.read())
        except OSError:
            pass

    # 若存在 defaults 备份，则校验前 5 个 step 不变（仅允许追加新 step）
    if os.path.isfile(backup_path):
        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                default_raw = f.read()
        except OSError:
            default_raw = ""

        def _split_default(text: str) -> list[str]:
            lines = text.splitlines()
            steps_acc: list[list[str]] = []
            cur2: list[str] | None = None
            for ln in lines:
                if ln.strip().startswith("## Step "):
                    cur2 = [ln]
                    steps_acc.append(cur2)
                    continue
                if cur2 is not None:
                    cur2.append(ln)
            return ["\n".join(s).strip() for s in steps_acc if "\n".join(s).strip()]

        default_steps = _split_default(default_raw)
        if len(default_steps) >= 5:
            for i in range(5):
                if steps[i].strip() != default_steps[i].strip():
                    return jsonify({"error": "默认前 5 个 Step 不允许修改，只能在其后追加新的 Step。"}), 400

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return jsonify({"ok": True, "stepsCount": len(steps)})


@app.get("/ecm/prompts/module2")
def get_module2_steps():
    """
    导师端：将 module2_steps.txt 按“全局 + Step 列表”形式返回，便于动态增减步骤。
    默认前 5 个 Step 视为基准，不建议改写，可在其后追加新 Step。
    """
    raw = load_prompt("module2_steps.txt")

    def _split(text: str) -> tuple[str, list[str]]:
        lines = text.splitlines()
        steps: list[list[str]] = []
        global_lines: list[str] = []
        global_suffix: list[str] = []
        cur: list[str] | None = None
        in_suffix = False
        for ln in lines:
            if ln.strip().startswith("# 输出模板") or ln.strip().startswith("# 执行指令"):
                in_suffix = True
                cur = None
            if in_suffix:
                global_suffix.append(ln)
                continue
            if ln.strip().startswith("### Step "):
                cur = [ln]
                steps.append(cur)
                continue
            if cur is None:
                global_lines.append(ln)
            else:
                cur.append(ln)
        global_text = ("\n".join(global_lines).strip() + "\n\n" + "\n".join(global_suffix).strip()).strip()
        step_texts = ["\n".join(s).strip() for s in steps if "\n".join(s).strip()]
        return global_text, step_texts

    g, steps = _split(raw)
    return jsonify({"global": g, "steps": steps})


@app.post("/ecm/prompts/module2/save")
def save_module2_steps():
    """
    导师端：保存 module2_steps.txt（全局 + steps）。
    约束：默认前 5 个 step 不允许修改；仅允许在其后追加新 step。
    Body: { "global": "...", "steps": ["...", "..."] }
    """
    body = request.get_json(silent=True) or {}
    global_text = body.get("global")
    steps = body.get("steps")
    if not isinstance(global_text, str):
        return jsonify({"error": "global must be string"}), 400
    if not isinstance(steps, list) or not all(isinstance(x, str) for x in steps):
        return jsonify({"error": "steps must be string array"}), 400
    steps = [s.strip() for s in steps if str(s).strip()]
    if len(steps) < 5:
        return jsonify({"error": "steps must have at least 5 items"}), 400

    base = _settings_for_prompts.prompts_dir
    os.makedirs(base, exist_ok=True)
    filename = "module2_steps.txt"
    path = os.path.join(base, filename)
    defaults_dir = os.path.join(base, "defaults")
    os.makedirs(defaults_dir, exist_ok=True)
    backup_path = os.path.join(defaults_dir, filename)

    # 首次保存先备份默认版本
    if os.path.isfile(path) and not os.path.isfile(backup_path):
        try:
            with open(path, "r", encoding="utf-8") as f_src, open(backup_path, "w", encoding="utf-8") as f_dst:
                f_dst.write(f_src.read())
        except OSError:
            pass

    # 若存在 defaults 备份，则校验前 5 个 step 不变
    if os.path.isfile(backup_path):
        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                default_raw = f.read()
        except OSError:
            default_raw = ""

        # 直接重新实现一次 split（只取 steps）
        def _split_default(text: str) -> list[str]:
            lines = text.splitlines()
            steps_acc: list[list[str]] = []
            cur2: list[str] | None = None
            for ln in lines:
                if ln.strip().startswith("### Step "):
                    cur2 = [ln]
                    steps_acc.append(cur2)
                    continue
                if ln.strip().startswith("# 输出模板") or ln.strip().startswith("# 执行指令"):
                    cur2 = None
                if cur2 is not None:
                    cur2.append(ln)
            return ["\n".join(s).strip() for s in steps_acc if "\n".join(s).strip()]

        default_steps = _split_default(default_raw)
        if len(default_steps) >= 5:
            for i in range(5):
                if steps[i].strip() != default_steps[i].strip():
                    return jsonify({"error": "默认前 5 个 Step 不允许修改，只能在其后追加新的 Step。"}), 400

    content = (global_text.strip() + "\n\n" + "\n\n".join(steps).strip() + "\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return jsonify({"ok": True, "stepsCount": len(steps)})


@app.post("/ecm/prompts/save")
def save_prompt():
    """
    保存某一个 prompt 文本。
    Body: { "key": "module1_steps", "content": "..." }
    首次保存时，会把当前文件备份到 prompts/defaults/<name>.txt 作为默认版本。
    """
    body = request.get_json(silent=True) or {}
    key = (body.get("key") or "").strip()
    content = body.get("content")
    if not key:
        return jsonify({"error": "key is required"}), 400
    if not isinstance(content, str):
        return jsonify({"error": "content must be string"}), 400

    mapping = {
        "module0_": "module0_.txt",
        "module1_steps": "module1_steps.txt",
        "module2_steps": "module2_steps.txt",
        "module3_Summary": "module3_Summary.txt",
        "module4_summary": "module4_summary.txt",
        "module5_inspiration": "module5_inspiration.txt",
    }
    filename = mapping.get(key)
    if not filename:
        return jsonify({"error": f"unknown key: {key}"}), 400

    base = _settings_for_prompts.prompts_dir
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, filename)

    # 备份默认版本
    defaults_dir = os.path.join(base, "defaults")
    os.makedirs(defaults_dir, exist_ok=True)
    backup_path = os.path.join(defaults_dir, filename)
    if os.path.isfile(path) and not os.path.isfile(backup_path):
        try:
            with open(path, "r", encoding="utf-8") as f_src, open(backup_path, "w", encoding="utf-8") as f_dst:
                f_dst.write(f_src.read())
        except OSError:
            # 备份失败不影响正常保存
            pass

    # 写入新内容
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return jsonify({"ok": True, "key": key})


def _user_profile_block(user_id: str) -> str:
    if not user_id:
        return ""
    return format_profile_for_prompt(get_profile(user_id))


def _module1_system_prompt(step: int, user_id: str = "") -> str:
    user_block = _user_profile_block(user_id)
    module0 = load_prompt("module0_.txt")
    module1_raw = load_prompt("module1_steps.txt")

    # 支持将 module1_steps.txt 拆为“全局 + 每个 Step”段落
    # 约定：用 "## Step N" 作为 Step 段落标题（与现有文件一致）
    def _split_module1(text: str) -> tuple[str, list[str]]:
        lines = text.splitlines()
        steps: list[list[str]] = []
        global_lines: list[str] = []
        cur: list[str] | None = None

        for ln in lines:
            stripped = ln.strip()
            if stripped.startswith("## Step "):
                cur = [ln]
                steps.append(cur)
                continue
            if cur is None:
                global_lines.append(ln)
            else:
                cur.append(ln)

        global_text = "\n".join(global_lines).strip()
        step_texts = ["\n".join(s).strip() for s in steps if "\n".join(s).strip()]
        return global_text, step_texts

    module1_global, module1_steps = _split_module1(module1_raw)
    total_steps = max(1, len(module1_steps))
    safe_step = max(1, min(int(step), total_steps))
    module1_current = module1_steps[safe_step - 1] if module1_steps else module1_raw

    controller = (
        "你正在执行 Function 1（define_problem）的多轮会话。\n"
        f"当前只执行 Step {safe_step}（总步数：{total_steps}）。\n"
        "请严格遵守：每次只问一个最关键的问题；导师身份。\n"
        "重要：在 Step 1，允许先做“基础认知科普 + 结合用户画像的个性化关联”，然后再只问一个关键问题；Step 2–5 不要科普，只按提示词推进。\n"
        f"如果你认为信息已经足够进入 Step {total_steps}，请直接输出最后一步的最终确认模板并询问用户输入「确认」。"
    )
    parts = [p for p in (user_block, module0, module1_global, module1_current, controller) if p]
    return build_system_prompt(*parts)


def _module2_system_prompt(step: int, user_id: str = "", action: str = "submit") -> str:
    user_block = _user_profile_block(user_id)
    module0 = load_prompt("module0_.txt")
    module2_raw = load_prompt("module2_steps.txt")

    # 将 module2_steps.txt 拆为“全局 + 每个 Step”段落
    # 约定：用 "### Step N" 作为 Step 段落标题（与现有文件一致）
    def _split_module2(text: str) -> tuple[str, list[str]]:
        lines = text.splitlines()
        steps: list[list[str]] = []
        global_lines: list[str] = []
        global_suffix: list[str] = []
        cur: list[str] | None = None
        in_suffix = False

        for ln in lines:
            stripped = ln.strip()
            # 输出模板/执行指令必须对所有 Step 生效，强制归入全局后缀
            if stripped.startswith("# 输出模板") or stripped.startswith("# 执行指令"):
                in_suffix = True
                cur = None

            if in_suffix:
                global_suffix.append(ln)
                continue

            if stripped.startswith("### Step "):
                cur = [ln]
                steps.append(cur)
                continue
            if cur is None:
                global_lines.append(ln)
            else:
                cur.append(ln)

        global_text = ("\n".join(global_lines).strip() + "\n\n" + "\n".join(global_suffix).strip()).strip()
        step_texts = ["\n".join(s).strip() for s in steps if "\n".join(s).strip()]
        return global_text, step_texts

    module2_global, module2_steps = _split_module2(module2_raw)
    total_steps = max(1, len(module2_steps))
    safe_step = max(1, min(int(step), total_steps))
    module2_current = module2_steps[safe_step - 1] if module2_steps else module2_raw

    controller = (
        "你正在执行 Function 2（深度探索）的多轮会话。\n"
        f"当前只执行 Step {safe_step}（总步数：{total_steps}）。\n"
        "请严格遵守：每次必须输出三段（📘 深度解析 / 📌 笔记卡片 / 👉 导师提问）；导师提问只能一个问题；不要一次性输出所有步骤。\n"
        "长度硬限制：本次总输出不超过 300 字（含标点与换行）。若超出，请主动压缩为要点版。\n"
        "若用户回复「继续/下一步」，直接进入下一 Step。\n"
        "请始终基于已确认的问题定义与范围边界推进。"
    )
    # For follow-up questions, we must avoid repeating the exact same "导师提问" template,
    # otherwise the model will "loop" on Step N's default question.
    if action in {"followup", "reply"}:
        controller += (
            "\n追问/回复规则（重要）：\n"
            "- 你必须基于本轮用户追问/回复的具体内容生成新的“导师提问”。\n"
            "- 禁止复述上一轮“导师提问”（禁止原句复用或几乎同句）。\n"
            "- 如果当前已到最后 Step，也必须继续追问，但“导师提问”要转为对用户问题的下一层细化问题，不能重复 Step 模板里的同一句话。\n"
        )
    parts = [p for p in (user_block, module0, module2_global, module2_current, controller) if p]
    return build_system_prompt(*parts)


def _module4_system_prompt(user_id: str = "") -> str:
    user_block = _user_profile_block(user_id)
    module0 = load_prompt("module0_.txt")
    module4 = load_prompt("module4_summary.txt")
    controller = (
        "你正在执行 Module 4（洞察与结构化封装）。\n"
        "请严格按提示词的 Markdown 模板输出（包含 Mermaid 代码块）。\n"
        "不要发散，不要提出新问题，只做结构化归纳。\n"
        "长度硬限制：本次总输出不超过 800 字（含标点与换行）。优先给可交付的摘要版。\n"
        "最后以“👉 用户确认”收尾。"
    )
    parts = [p for p in (user_block, module0, module4, controller) if p]
    return build_system_prompt(*parts)


def _module5_system_prompt(user_id: str = "") -> str:
    user_block = _user_profile_block(user_id)
    module0 = load_prompt("module0_.txt")
    module5 = load_prompt("module5_inspiration.txt")
    controller = (
        "你正在执行 Module 5（灵感升华与闭环）。\n"
        "请严格按三个小标题输出：画像点评 / Spark / Next Loop。\n"
        "语气要像导师，简洁、有温度、有洞见。"
    )
    parts = [p for p in (user_block, module0, module5, controller) if p]
    return build_system_prompt(*parts)


def _persona_system_prompt(user_id: str = "") -> str:
    user_block = _user_profile_block(user_id)
    module0 = load_prompt("module0_.txt")
    persona = load_prompt("persona_builder.txt")
    controller = (
        "你正在执行 Persona Builder（画像破冰）。\n"
        "你要在 3–5 轮内完成画像信息收集。\n"
        "每次只问 1 个问题。\n"
        "当信息足够时，必须输出【Final Persona】块（包含：核心动力/终局规划/学习习惯/个性化引导建议）。"
    )
    parts = [p for p in (user_block, module0, persona, controller) if p]
    return build_system_prompt(*parts)


def _extract_final_persona(text: str) -> dict[str, str]:
    # Very lightweight extraction; tolerate minor formatting variance.
    out: dict[str, str] = {"core_motivation": "", "end_goal": "", "learning_habits": "", "persona_summary": ""}
    if not text:
        return out
    raw = text.strip()
    out["persona_summary"] = raw
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("核心动力"):
            out["core_motivation"] = s.split("：", 1)[-1].strip() if "：" in s else s.replace("核心动力", "").strip()
        if s.startswith("终局规划"):
            out["end_goal"] = s.split("：", 1)[-1].strip() if "：" in s else s.replace("终局规划", "").strip()
        if s.startswith("学习习惯"):
            out["learning_habits"] = s.split("：", 1)[-1].strip() if "：" in s else s.replace("学习习惯", "").strip()
    return out


@app.post("/ecm/module1/start")
def module1_start():
    """
    Start a step-by-step Module1 session.
    Body: { "question": "...", "topic": optional }
    """
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    topic = body.get("topic")
    topic = None if topic is None else str(topic).strip()

    if not settings.deepseek_api_key:
        return jsonify({"error": "Missing DEEPSEEK_API_KEY. Create .env in ecm_backend and set it."}), 500

    # question 现在可以为空；首次真正问题会在后续模块中补充
    s = new_module1_session(question=question or "", topic=topic)

    # Step 1 的引导语仍保存在后端上下文中，但前端会自己展示一份固定引导语。
    opening = (
        "ECM探索导师\n你好，我是你的 ECM 深度探索导师。请告诉我，你想探讨的主题是什么？"
        "（越具体越好，如果模糊也没关系，我会帮你理清）"
    )
    s.history.append({"role": "assistant", "content": opening})
    save_module1_session(s)
    return jsonify(
        {
            "session_id": s.session_id,
            "module": "module1",
            "step": s.step,
            "assistant": "",
            "done": s.done,
            "awaiting_confirm": s.awaiting_confirm,
        }
    )


@app.post("/ecm/module1/next")
def module1_next():
    """
    Continue Module1 session.
    Body: { "session_id": "...", "user_input": "..." }
    """
    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    user_input = (body.get("user_input") or "").strip()
    user_id = (body.get("userId") or body.get("user_id") or "").strip()

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not user_input:
        return jsonify({"error": "user_input is required"}), 400

    s = get_module1_session(session_id)
    if not s:
        return jsonify({"error": "session not found"}), 404

    # 读取当前 module1_steps.txt 的总步数（动态 Steps）
    try:
        _raw = load_prompt("module1_steps.txt")
        _total_steps = sum(1 for ln in _raw.splitlines() if ln.strip().startswith("## Step "))
        total_steps = max(1, _total_steps)
    except Exception:
        total_steps = 5

    if s.done and s.awaiting_confirm:
        if user_input in {"确认", "ok", "OK", "Ok"}:
            s.awaiting_confirm = False
            save_module1_session(s)
            return jsonify(
                {
                    "session_id": s.session_id,
                    "module": "module1",
                    "step": s.step,
                    "assistant": "已确认。你可以进入第二阶段（Function 2：深度探索）。",
                    "done": True,
                    "awaiting_confirm": False,
                    "next": "module2",
                }
            )
        # 允许用户在最后一步对最终输出进行修改：如果不是“确认”，则用用户输入替换最终输出内容，再次要求确认
        s.confirmed_definition = user_input.strip()
        s.done = True
        s.awaiting_confirm = True
        save_module1_session(s)
        return jsonify(
            {
                "session_id": s.session_id,
                "module": "module1",
                "step": s.step,
                "assistant": "我已用你的输入更新最终定义内容。请确认是否准确？如果准确请输入「确认」，我们将进入第二阶段：深度探索。",
                "done": True,
                "awaiting_confirm": True,
                "confirmed_definition": s.confirmed_definition,
            }
        )

    # Append user's message
    # If module1 was started with an empty question (e.g. client restart),
    # fill it with the first real user input so downstream steps have context.
    if not _safe_str(getattr(s, "question", "")).strip() and int(s.step) == 1:
        s.question = user_input.strip()
        save_module1_session(s)
    s.history.append({"role": "user", "content": user_input})
    # Capture the previous assistant "导师提问" to prevent question repetition loops.
    prev_assistant_text = ""
    for m in reversed(s.history[:-1]):
        if isinstance(m, dict) and m.get("role") == "assistant":
            prev_assistant_text = _safe_str(m.get("content") or "")
            break
    prev_question = ""
    if prev_assistant_text:
        # Best-effort extraction: content after "👉 导师提问"
        parts = prev_assistant_text.split("👉 导师提问", 1)
        if len(parts) == 2:
            prev_question = parts[1].strip()
        else:
            prev_question = prev_assistant_text.strip()[:240]

    # Execute current step (do NOT pre-increment).
    # This ensures the first real user input executes Step 1 (科普地图 + 画像关联 + 单问) instead of skipping to Step 2.
    executed_step = int(s.step)
    system_prompt = _module1_system_prompt(executed_step, user_id)
    # Provide compact context: original question/topic + recent turns
    context_lines = [f"用户原始问题：{s.question}"]
    if s.topic:
        context_lines.insert(0, f"主题：{s.topic}")
    # Keep last 10 messages to bound size
    history_tail = s.history[-10:]
    convo = "\n".join([f"{m['role']}: {m['content']}" for m in history_tail])
    model_user_input = "\n\n".join(context_lines + ["最近对话：", convo])

    try:
        resp = asyncio.run(call_deepseek(system_prompt=system_prompt, user_input=model_user_input, max_tokens=450, temperature=0.2))
        assistant_text = extract_assistant_content(resp).strip()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not assistant_text:
        assistant_text = "我没有收到有效输出。请你再补充一句你的回答。"

    s.history.append({"role": "assistant", "content": assistant_text})

    # advance to next step for subsequent turns (unless already at last step)
    if int(s.step) < int(total_steps):
        s.step = int(s.step) + 1

    # Detect completion template
    if "🚩" in assistant_text and "问题定义确认" in assistant_text:
        s.done = True
        s.awaiting_confirm = True
        s.confirmed_definition = assistant_text

        extracted = extract_tags_quotes_hooks(assistant_text)
        notes = load_notes()
        notes = merge_notes(
            notes,
            topic=s.topic or s.question,
            tags=extracted.tags,
            quotes=extracted.quotes,
            hooks=extracted.hooks,
        )
        save_notes(notes)

    save_module1_session(s)
    return jsonify(
        {
            "session_id": s.session_id,
            "module": "module1",
            # return the step that was executed for this response (more intuitive for UI)
            "step": executed_step,
            "next_step": s.step,
            "assistant": assistant_text,
            "done": s.done,
            "awaiting_confirm": s.awaiting_confirm,
            "confirmed_definition": s.confirmed_definition if s.done else "",
            "total_steps": total_steps,
        }
    )


@app.post("/ecm/module1/next_stream")
def module1_next_stream():
    """
    Streaming variant of Module1 next.
    SSE events:
    - data: <delta text>
    - event: final, data: JSON string
    """
    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    user_input = (body.get("user_input") or "").strip()
    user_id = (body.get("userId") or body.get("user_id") or "").strip()
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not user_input:
        return jsonify({"error": "user_input is required"}), 400

    s = get_module1_session(session_id)
    if not s:
        return jsonify({"error": "session not found"}), 404

    # dynamic total steps
    try:
        _raw = load_prompt("module1_steps.txt")
        _total_steps = sum(1 for ln in _raw.splitlines() if ln.strip().startswith("## Step "))
        total_steps = max(1, _total_steps)
    except Exception:
        total_steps = 5

    # awaiting confirm branch: allow modify or confirm
    if s.done and s.awaiting_confirm:
        if user_input in {"确认", "ok", "OK", "Ok"}:
            s.awaiting_confirm = False
            save_module1_session(s)
            def gen_confirm():
                yield _sse("已确认。你可以进入第二阶段（Function 2：深度探索）。")
                yield _sse(
                    json.dumps(
                        {
                            "session_id": s.session_id,
                            "module": "module1",
                            "step": s.step,
                            "assistant": "已确认。你可以进入第二阶段（Function 2：深度探索）。",
                            "done": True,
                            "awaiting_confirm": False,
                            "next": "module2",
                            "confirmed_definition": s.confirmed_definition,
                            "total_steps": total_steps,
                        },
                        ensure_ascii=False,
                    ),
                    event="final",
                )
            return Response(stream_with_context(gen_confirm()), mimetype="text/event-stream")

        s.confirmed_definition = user_input.strip()
        s.done = True
        s.awaiting_confirm = True
        save_module1_session(s)
        msg = "我已用你的输入更新最终定义内容。请确认是否准确？如果准确请输入「确认」，我们将进入第二阶段：深度探索。"
        def gen_mod():
            yield _sse(msg)
            yield _sse(
                json.dumps(
                    {
                        "session_id": s.session_id,
                        "module": "module1",
                        "step": s.step,
                        "assistant": msg,
                        "done": True,
                        "awaiting_confirm": True,
                        "confirmed_definition": s.confirmed_definition,
                        "total_steps": total_steps,
                    },
                    ensure_ascii=False,
                ),
                event="final",
            )
        return Response(stream_with_context(gen_mod()), mimetype="text/event-stream")

    # normal progression
    # If module1 was started with an empty question (e.g. client restart),
    # fill it with the first real user input so downstream steps have context.
    if not _safe_str(getattr(s, "question", "")).strip() and int(s.step) == 1:
        s.question = user_input.strip()
        save_module1_session(s)

    s.history.append({"role": "user", "content": user_input})
    executed_step = int(s.step)
    system_prompt = _module1_system_prompt(executed_step, user_id)
    context_lines = [f"用户原始问题：{s.question}"]
    if s.topic:
        context_lines.insert(0, f"主题：{s.topic}")
    history_tail = s.history[-10:]
    convo = "\n".join([f"{m['role']}: {m['content']}" for m in history_tail])
    model_user_input = "\n\n".join(context_lines + ["最近对话：", convo])

    def gen():
        try:
            collected_parts: list[str] = []
            for piece in stream_deepseek(system_prompt=system_prompt, user_input=model_user_input):
                collected_parts.append(piece)
                yield _sse(piece)
            assistant_text = "".join(collected_parts).strip() or "我没有收到有效输出。请你再补充一句你的回答。"
        except Exception as e:
            err = str(e)
            yield _sse(err)
            assistant_text = err

        s.history.append({"role": "assistant", "content": assistant_text})

        if int(s.step) < int(total_steps):
            s.step = int(s.step) + 1

        if "🚩" in assistant_text and "问题定义确认" in assistant_text:
            s.done = True
            s.awaiting_confirm = True
            s.confirmed_definition = assistant_text

            extracted = extract_tags_quotes_hooks(assistant_text)
            notes = load_notes()
            notes = merge_notes(
                notes,
                topic=s.topic or s.question,
                tags=extracted.tags,
                quotes=extracted.quotes,
                hooks=extracted.hooks,
            )
            save_notes(notes)

        save_module1_session(s)

        yield _sse(
            json.dumps(
                {
                    "session_id": s.session_id,
                    "module": "module1",
                    "step": executed_step,
                    "next_step": s.step,
                    "assistant": assistant_text,
                    "done": s.done,
                    "awaiting_confirm": s.awaiting_confirm,
                    "confirmed_definition": s.confirmed_definition if s.done else "",
                    "total_steps": total_steps,
                },
                ensure_ascii=False,
            ),
            event="final",
        )

    return Response(stream_with_context(gen()), mimetype="text/event-stream")


@app.post("/ecm/module1/undo")
def module1_undo():
    """
    学生端：撤销最近一次“Step”的对话（通常是最近一对 user+assistant）。
    Body: { "session_id": "..." }
    """
    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    s = get_module1_session(session_id)
    if not s:
        return jsonify({"error": "session not found"}), 404

    # 清理确认状态
    s.done = False
    s.awaiting_confirm = False
    s.confirmed_definition = ""

    # 从 history 尾部弹出最近的 assistant/user（最多 2 条）
    for _ in range(2):
        if s.history:
            s.history.pop()

    if int(s.step) > 1:
        s.step = int(s.step) - 1

    save_module1_session(s)
    return jsonify({"ok": True, "step": s.step})


@app.post("/ecm/module2/start")
def module2_start():
    """
    Start Module2 exploration session.
    Body: { "definition": "🚩问题定义确认...", "module1_session_id": optional, "userId": optional }
    """
    if not settings.deepseek_api_key:
        return jsonify({"error": "Missing DEEPSEEK_API_KEY. Create .env in ecm_backend and set it."}), 500

    body = request.get_json(silent=True) or {}
    definition = (body.get("definition") or "").strip()
    module1_sid = (body.get("module1_session_id") or "").strip()
    user_id = (body.get("userId") or body.get("user_id") or "").strip()

    if not definition and module1_sid:
        m1 = get_module1_session(module1_sid)
        if m1 and m1.confirmed_definition:
            definition = m1.confirmed_definition.strip()

    if not definition:
        return jsonify({"error": "definition is required (or provide module1_session_id with confirmed_definition)"}), 400

    s = new_module2_session(definition=definition)

    # 动态总步数（导师端可追加 Step）
    try:
        _raw = load_prompt("module2_steps.txt")
        total_steps = max(1, sum(1 for ln in _raw.splitlines() if ln.strip().startswith("### Step ")))
    except Exception:
        total_steps = 5

    system_prompt = _module2_system_prompt(1, user_id, action="submit")
    model_user_input = f"已确认的问题定义如下：\n{definition}\n\n请从 Step 1 开始输出。"
    try:
        resp = asyncio.run(call_deepseek(system_prompt=system_prompt, user_input=model_user_input))
        assistant_text = extract_assistant_content(resp).strip()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not assistant_text:
        assistant_text = "我没有收到有效输出。我们从 Step 1 开始：你希望先用一个比喻来理解本质，还是直接拆出关键变量？（二选一）"

    display_text = strip_note_card_block(assistant_text)
    s.history.append({"role": "assistant", "content": display_text})

    extracted = extract_tags_quotes_hooks(assistant_text)
    meta = extract_note_card(assistant_text)
    notes = load_notes()
    notes = merge_notes(notes, topic=None, tags=extracted.tags, quotes=extracted.quotes, hooks=extracted.hooks)
    save_notes(notes)

    save_module2_session(s)
    return jsonify(
        {
            "session_id": s.session_id,
            "module": "module2",
            "step": s.step,
            "assistant": display_text,
            "done": s.done,
            "meta": meta,
            "total_steps": total_steps,
        }
    )


@app.post("/ecm/module2/start_stream")
def module2_start_stream():
    """
    Streaming variant of Module2 start.
    SSE: data=<delta>, event: final data=<json>
    """
    if not settings.deepseek_api_key:
        return jsonify({"error": "Missing DEEPSEEK_API_KEY. Create .env in ecm_backend and set it."}), 500

    body = request.get_json(silent=True) or {}
    definition = (body.get("definition") or "").strip()
    module1_sid = (body.get("module1_session_id") or "").strip()
    user_id = (body.get("userId") or body.get("user_id") or "").strip()
    action = (body.get("action") or "submit").strip()  # reply|followup|submit
    parent_id = (body.get("parent_id") or body.get("parentId") or "").strip() or None

    if not definition and module1_sid:
        m1 = get_module1_session(module1_sid)
        if m1 and m1.confirmed_definition:
            definition = m1.confirmed_definition.strip()

    if not definition:
        return jsonify({"error": "definition is required (or provide module1_session_id with confirmed_definition)"}), 400

    s = new_module2_session(definition=definition)
    root_id = s.ensure_root()
    if parent_id is None:
        parent_id = root_id

    try:
        _raw = load_prompt("module2_steps.txt")
        total_steps = max(1, sum(1 for ln in _raw.splitlines() if ln.strip().startswith("### Step ")))
    except Exception:
        total_steps = 5

    system_prompt = _module2_system_prompt(1, user_id, action="submit")
    model_user_input = f"已确认的问题定义如下：\n{definition}\n\n请从 Step 1 开始输出。"

    def gen():
        try:
            parts: list[str] = []
            for piece in stream_deepseek(system_prompt=system_prompt, user_input=model_user_input, max_tokens=450, temperature=0.2):
                parts.append(piece)
                yield _sse(piece)
            assistant_text = "".join(parts).strip()
        except Exception as e:
            assistant_text = str(e)
            yield _sse(assistant_text)

        if not assistant_text:
            assistant_text = "我没有收到有效输出。我们从 Step 1 开始：你希望先用一个比喻来理解本质，还是直接拆出关键变量？（二选一）"

        display_text = strip_note_card_block(assistant_text)
        s.history.append({"role": "assistant", "content": display_text})

        score, ref = _parse_score_reference(assistant_text)
        node_id = str(uuid.uuid4())
        s.nodes[node_id] = {
            "id": node_id,
            "parent_id": parent_id,
            "action": action,
            "step": int(s.step),
            "user": "",
            "assistant": assistant_text,
            "score": score,
            "reference": ref,
            "ts": time.time(),
        }

        extracted = extract_tags_quotes_hooks(assistant_text)
        meta = extract_note_card(assistant_text)
        notes = load_notes()
        notes = merge_notes(notes, topic=None, tags=extracted.tags, quotes=extracted.quotes, hooks=extracted.hooks)
        save_notes(notes)

        save_module2_session(s)

        yield _sse(
            json.dumps(
                {
                    "session_id": s.session_id,
                    "module": "module2",
                    "step": s.step,
                    "assistant": display_text,
                    "done": s.done,
                    "meta": meta,
                    "total_steps": total_steps,
                    "node_id": node_id,
                    "parent_id": parent_id,
                    "score": score,
                    "reference": ref,
                },
                ensure_ascii=False,
            ),
            event="final",
        )

    return Response(stream_with_context(gen()), mimetype="text/event-stream")


@app.post("/ecm/module2/next")
def module2_next():
    """
    Continue Module2 session.
    Body: { "session_id": "...", "user_input": "..." }
    """
    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    user_input = (body.get("user_input") or "").strip()
    user_id = (body.get("userId") or body.get("user_id") or "").strip()

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not user_input:
        return jsonify({"error": "user_input is required"}), 400

    s = get_module2_session(session_id)
    if not s:
        return jsonify({"error": "session not found"}), 404

    # 动态总步数（导师端可追加 Step）
    try:
        _raw = load_prompt("module2_steps.txt")
        total_steps = max(1, sum(1 for ln in _raw.splitlines() if ln.strip().startswith("### Step ")))
    except Exception:
        total_steps = 5

    s.history.append({"role": "user", "content": user_input})

    # Step progression: 默认每轮向前推进，最多到 Step5，之后保持在 Step5 继续对话
    if int(s.step) < int(total_steps):
        s.step = int(s.step) + 1

    system_prompt = _module2_system_prompt(int(s.step), user_id, action=action)
    # Make followup generation conditioned on the latest user query.
    # Without this, step-based templates may repeat verbatim.
    if action == "followup":
        system_prompt += (
            "\n追问模式（followup）要求：\n"
            "1) 必须直接回应本轮用户追问提出的新增需求（例如“案例/例子/具体讲解/不确定点”等）。\n"
            "2) 必须基于本轮用户追问的具体内容进行补充解释，不能只复述上一轮相同模板。\n"
            "3) “👉 导师提问”必须与本轮追问强相关，并生成新的问题句式；避免与上一轮导师提问重复。\n"
        )
    history_tail = s.history[-10:]
    convo = "\n".join([f"{m['role']}: {m['content']}" for m in history_tail])
    prev_assistant = ""
    for m in reversed(s.history[:-1]):
        if isinstance(m, dict) and m.get("role") == "assistant" and _safe_str(m.get("content")).strip():
            prev_assistant = _safe_str(m.get("content")).strip()
            break
    model_user_input = "\n\n".join(
        [
            "已确认的问题定义：",
            s.definition,
            "",
            "最近对话：",
            convo,
            "",
            "本轮用户输入（新增需求/追问）：",
            user_input,
            "",
            f"请输出 Step {s.step}。",
        ]
    )
    if action == "followup" and prev_assistant:
        # Provide previous output as explicit anti-repetition guidance.
        model_user_input = (
            model_user_input
            + "\n\n上一轮导师输出（对比参考，禁止逐字重复）：\n"
            + prev_assistant[:1200]
    )

    try:
        resp = asyncio.run(call_deepseek(system_prompt=system_prompt, user_input=model_user_input, max_tokens=450, temperature=0.2))
        assistant_text = extract_assistant_content(resp).strip()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not assistant_text:
        assistant_text = "我没有收到有效输出。你可以回复「继续」进入下一步，或补充一句你的想法。"

    display_text = strip_note_card_block(assistant_text)
    s.history.append({"role": "assistant", "content": display_text})

    extracted = extract_tags_quotes_hooks(assistant_text)
    meta = extract_note_card(assistant_text)
    notes = load_notes()
    notes = merge_notes(notes, topic=None, tags=extracted.tags, quotes=extracted.quotes, hooks=extracted.hooks)
    save_notes(notes)

    save_module2_session(s)
    return jsonify(
        {
            "session_id": s.session_id,
            "module": "module2",
            "step": s.step,
            "assistant": display_text,
            "done": s.done,
            "meta": meta,
            "total_steps": total_steps,
        }
    )


@app.post("/ecm/module2/next_stream")
def module2_next_stream():
    """
    Streaming variant of Module2 next.
    SSE: data=<delta>, event: final data=<json>
    """
    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    user_input = (body.get("user_input") or "").strip()
    user_id = (body.get("userId") or body.get("user_id") or "").strip()
    action = (body.get("action") or "reply").strip()  # reply|followup|submit
    parent_id = (body.get("parent_id") or body.get("parentId") or "").strip() or None

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not user_input:
        return jsonify({"error": "user_input is required"}), 400

    s = get_module2_session(session_id)
    if not s:
        return jsonify({"error": "session not found"}), 404
    root_id = s.ensure_root()
    if parent_id is None:
        parent_id = root_id

    try:
        _raw = load_prompt("module2_steps.txt")
        total_steps = max(1, sum(1 for ln in _raw.splitlines() if ln.strip().startswith("### Step ")))
    except Exception:
        total_steps = 5

    s.history.append({"role": "user", "content": user_input})
    # advance step ONLY on submit
    if action == "submit" and int(s.step) < int(total_steps):
        s.step = int(s.step) + 1

    system_prompt = _module2_system_prompt(int(s.step), user_id, action=action)
    history_tail = s.history[-10:]
    convo = "\n".join([f"{m['role']}: {m['content']}" for m in history_tail])

    # Capture the previous assistant "导师提问" to prevent question repetition loops.
    # Note: At this point we already appended the current user_input to s.history.
    # So the previous assistant should be in s.history[:-1].
    prev_assistant_text = ""
    for m in reversed(s.history[:-1]):
        if isinstance(m, dict) and m.get("role") == "assistant":
            prev_assistant_text = _safe_str(m.get("content") or "")
            break
    prev_question = ""
    if prev_assistant_text:
        # Best-effort extraction: content after "👉 导师提问"
        parts = prev_assistant_text.split("👉 导师提问", 1)
        if len(parts) == 2:
            prev_question = parts[1].strip()
        else:
            prev_question = prev_assistant_text.strip()[:240]

    model_user_input = "\n\n".join(
        [
            "已确认的问题定义：",
            s.definition,
            "",
            "最近对话：",
            convo,
            "",
            f"上一轮导师提问（禁止重复/几乎同句复用）：\n{prev_question}",
            "",
            f"请以 Step {s.step} 的主线为框架作答：先直接回答用户输入，再给出新的“导师提问”（必须与上一轮不同且更贴合本轮用户问题）。",
        ]
    )

    def gen():
        try:
            parts: list[str] = []
            for piece in stream_deepseek(system_prompt=system_prompt, user_input=model_user_input, max_tokens=450, temperature=0.2):
                parts.append(piece)
                yield _sse(piece)
            assistant_text = "".join(parts).strip()
        except Exception as e:
            assistant_text = str(e)
            yield _sse(assistant_text)

        if not assistant_text:
            assistant_text = "我没有收到有效输出。你可以回复「继续」进入下一步，或补充一句你的想法。"

        display_text = strip_note_card_block(assistant_text)
        s.history.append({"role": "assistant", "content": display_text})

        score, ref = _parse_score_reference(assistant_text)
        node_id = str(uuid.uuid4())
        s.nodes[node_id] = {
            "id": node_id,
            "parent_id": parent_id,
            "action": action,
            "step": int(s.step),
            "user": user_input,
            "assistant": assistant_text,
            "score": score,
            "reference": ref,
            "ts": time.time(),
        }

        extracted = extract_tags_quotes_hooks(assistant_text)
        meta = extract_note_card(assistant_text)
        notes = load_notes()
        notes = merge_notes(notes, topic=None, tags=extracted.tags, quotes=extracted.quotes, hooks=extracted.hooks)
        save_notes(notes)

        save_module2_session(s)

        yield _sse(
            json.dumps(
                {
                    "session_id": s.session_id,
                    "module": "module2",
                    "step": s.step,
                    "assistant": display_text,
                    "done": s.done,
                    "meta": meta,
                    "total_steps": total_steps,
                    "node_id": node_id,
                    "parent_id": parent_id,
                    "action": action,
                    "score": score,
                    "reference": ref,
                },
                ensure_ascii=False,
            ),
            event="final",
        )

    return Response(stream_with_context(gen()), mimetype="text/event-stream")


@app.post("/ecm/module2/undo")
def module2_undo():
    """
    学生端：撤销最近一次“Step”的对话（通常是最近一对 user+assistant）。
    Body: { "session_id": "..." }
    """
    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    s = get_module2_session(session_id)
    if not s:
        return jsonify({"error": "session not found"}), 404

    s.done = False

    for _ in range(2):
        if s.history:
            s.history.pop()

    if int(s.step) > 1:
        s.step = int(s.step) - 1

    # 动态总步数
    try:
        _raw = load_prompt("module2_steps.txt")
        total_steps = max(1, sum(1 for ln in _raw.splitlines() if ln.strip().startswith("### Step ")))
    except Exception:
        total_steps = 5

    save_module2_session(s)
    return jsonify({"ok": True, "step": s.step, "total_steps": total_steps})


@app.post("/ecm/module4/generate")
def module4_generate():
    """
    Generate Module4 report.
    Body: { "module1_session_id": "...", "module2_session_id": "...", "force": optional, "user_input": optional }
    """
    if not settings.deepseek_api_key:
        return jsonify({"error": "Missing DEEPSEEK_API_KEY. Create .env in ecm_backend and set it."}), 500

    body = request.get_json(silent=True) or {}
    m1_id = (body.get("module1_session_id") or "").strip()
    m2_id = (body.get("module2_session_id") or "").strip()
    force = bool(body.get("force") or False)
    user_input = (body.get("user_input") or "").strip()
    user_id = (body.get("userId") or body.get("user_id") or "").strip()

    if not m1_id or not m2_id:
        return jsonify({"error": "module1_session_id and module2_session_id are required"}), 400

    m1 = get_module1_session(m1_id)
    m2 = get_module2_session(m2_id)
    if not m1 or not m1.confirmed_definition:
        return jsonify({"error": "Module1 not confirmed yet"}), 400
    if not m2:
        return jsonify({"error": "Module2 session not found"}), 404
    if not (m2.done or force or any(k in user_input for k in ["总结", "生成笔记", "结束探索"])):
        return jsonify({"error": "Module2 not finished. Send '总结/生成笔记/结束探索' or finish Step5."}), 400

    definition = m1.confirmed_definition.strip()
    notes = load_notes()

    # Provide compact context (definition + extracted metadata + Module2 conversation tail)
    history_tail = (m2.history or [])[-16:]
    convo = "\n".join([f"{m['role']}: {m['content']}" for m in history_tail])
    meta_blob = (
        f"tags: {notes.get('tags', [])}\n"
        f"quotes: {notes.get('quotes', [])}\n"
        f"hooks: {notes.get('hooks', [])}\n"
    )
    model_user_input = "\n\n".join(
        [
            "已确认的问题定义：",
            definition,
            "",
            "已提炼的元数据（来自交互区）：",
            meta_blob,
            "",
            "最近对话（摘要）：",
            convo,
        ]
    )

    try:
        resp = asyncio.run(call_deepseek(system_prompt=_module4_system_prompt(user_id), user_input=model_user_input, max_tokens=1200, temperature=0.2))
        report_raw = extract_assistant_content(resp).strip()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not report_raw:
        return jsonify({"error": "Empty report"}), 500

    mermaid_code = extract_mermaid_code(report_raw)
    report = report_raw

    s4 = new_module4_session(definition=definition, report_md=report)
    s4.state = "awaiting_confirm"
    s4.history.append({"role": "assistant", "content": report})
    save_module4_session(s4)

    # persist quotes/hooks/tags from report too (optional)
    extracted = extract_tags_quotes_hooks(report)
    notes = merge_notes(notes, topic=notes.get("topic") or "", tags=extracted.tags, quotes=extracted.quotes, hooks=extracted.hooks)
    save_notes(notes)

    return jsonify(
        {
            "session_id": s4.session_id,
            "module": "module4",
            "assistant": report,
            "state": s4.state,
            "mermaid_code": mermaid_code,
        }
    )


@app.post("/ecm/module4/generate_stream")
def module4_generate_stream():
    """
    Streaming variant of Module4 generate.
    SSE: data=<delta>, event: final data=<json>
    """
    if not settings.deepseek_api_key:
        return jsonify({"error": "Missing DEEPSEEK_API_KEY. Create .env in ecm_backend and set it."}), 500

    body = request.get_json(silent=True) or {}
    m1_id = (body.get("module1_session_id") or "").strip()
    m2_id = (body.get("module2_session_id") or "").strip()
    # If module1 session is lost on server restart, front-end can still provide
    # the confirmed definition text so Module4 can be generated without Module1 session state.
    module1_definition_override = _safe_str(body.get("module1_definition") or body.get("module1Definition") or "")
    force = bool(body.get("force") or False)
    user_input = (body.get("user_input") or "").strip()
    user_id = (body.get("userId") or body.get("user_id") or "").strip()
    module2_history_raw = body.get("module2_history") or body.get("module2History") or []

    if not m2_id:
        return jsonify({"error": "module2_session_id is required"}), 400

    m1 = get_module1_session(m1_id) if m1_id else None
    m2 = get_module2_session(m2_id)
    module2_history_override: list[dict[str, str]] = []
    if isinstance(module2_history_raw, list):
        for x in module2_history_raw:
            if not isinstance(x, dict):
                continue
            role = _safe_str(x.get("role") or "").strip()
            content = _safe_str(x.get("content") or "")
            if role in ("user", "assistant") and content.strip():
                module2_history_override.append({"role": role, "content": content})

    if module1_definition_override.strip():
        definition = module1_definition_override.strip()
    else:
        if not m1 or not m1.confirmed_definition:
            return jsonify({"error": "Module1 not confirmed yet"}), 400
    if not m2 and not module2_history_override:
        return jsonify({"error": "Module2 session not found"}), 404
    m2_done = bool(m2.done) if m2 else bool(module2_history_override)
    if not (m2_done or force or any(k in user_input for k in ["总结", "生成笔记", "结束探索"])):
        return jsonify({"error": "Module2 not finished. Send '总结/生成笔记/结束探索' or finish Step5."}), 400

    notes = load_notes()

    source_history = (m2.history or []) if m2 else module2_history_override
    history_tail = source_history[-16:]
    convo = "\n".join([f"{m['role']}: {m['content']}" for m in history_tail])
    meta_blob = (
        f"tags: {notes.get('tags', [])}\n"
        f"quotes: {notes.get('quotes', [])}\n"
        f"hooks: {notes.get('hooks', [])}\n"
    )
    model_user_input = "\n\n".join(
        [
            "已确认的问题定义：",
            definition,
            "",
            "已提炼的元数据（来自交互区）：",
            meta_blob,
            "",
            "最近对话（摘要）：",
            convo,
        ]
    )

    sys_prompt = _module4_system_prompt(user_id)

    def gen():
        try:
            parts: list[str] = []
            for piece in stream_deepseek(system_prompt=sys_prompt, user_input=model_user_input, max_tokens=1200, temperature=0.2):
                parts.append(piece)
                yield _sse(piece)
            report_raw = "".join(parts).strip()
        except Exception as e:
            report_raw = str(e)
            yield _sse(report_raw)

        if not report_raw:
            report_raw = "Empty report"

        mermaid_code = extract_mermaid_code(report_raw)
        # Normalize markdown so headings/sections render correctly in ReactMarkdown.
        report = _normalize_student_markdown(report_raw)

        s4 = new_module4_session(definition=definition, report_md=report)
        s4.state = "awaiting_confirm"
        s4.history.append({"role": "assistant", "content": report})
        save_module4_session(s4)

        extracted = extract_tags_quotes_hooks(report)
        notes2 = merge_notes(notes, topic=notes.get("topic") or "", tags=extracted.tags, quotes=extracted.quotes, hooks=extracted.hooks)
        save_notes(notes2)

        yield _sse(
            json.dumps(
                {
                    "session_id": s4.session_id,
                    "module": "module4",
                    "assistant": report,
                    "state": s4.state,
                    "mermaid_code": mermaid_code,
                },
                ensure_ascii=False,
            ),
            event="final",
        )

    return Response(stream_with_context(gen()), mimetype="text/event-stream")


@app.post("/ecm/module4/confirm")
def module4_confirm():
    body = request.get_json(silent=True) or {}
    sid = (body.get("session_id") or "").strip()
    user_input = (body.get("user_input") or "").strip()
    if not sid:
        return jsonify({"error": "session_id is required"}), 400
    s4 = get_module4_session(sid)
    if not s4:
        return jsonify({"error": "session not found"}), 404

    if user_input in {"确认", "ok", "OK", "Ok", "可以结束了"}:
        s4.state = "confirmed"
        save_module4_session(s4)
        return jsonify({"session_id": s4.session_id, "module": "module4", "assistant": "已确认。你可以进入最后一步：灵感升华。", "state": s4.state, "next": "module5"})

    s4.state = "awaiting_confirm"
    save_module4_session(s4)
    return jsonify({"session_id": s4.session_id, "module": "module4", "assistant": "我正在等待你输入「确认」后进入模块五。", "state": s4.state})


@app.post("/ecm/module5/generate")
def module5_generate():
    """
    Generate Module5 inspiration.
    Body: { "module4_session_id": "...", "force": optional, "user_input": optional }
    """
    if not settings.deepseek_api_key:
        return jsonify({"error": "Missing DEEPSEEK_API_KEY. Create .env in ecm_backend and set it."}), 500

    body = request.get_json(silent=True) or {}
    m4_id = (body.get("module4_session_id") or "").strip()
    force = bool(body.get("force") or False)
    user_input = (body.get("user_input") or "").strip()
    user_id = (body.get("userId") or body.get("user_id") or "").strip()
    module5_history_raw = body.get("module5_history") or body.get("module5History") or body.get("history") or []

    module5_history: list[dict[str, str]] = []
    if isinstance(module5_history_raw, list):
        for x in module5_history_raw:
            if not isinstance(x, dict):
                continue
            role = _safe_str(x.get("role") or "").strip()
            content = _safe_str(x.get("content") or "")
            if role in ("user", "assistant") and content.strip():
                module5_history.append({"role": role, "content": content.strip()})

    history_tail = module5_history[-10:]
    history_block = "\n".join(
        f"{('用户' if m['role'] == 'user' else '导师')}: {m['content']}" for m in history_tail
    ).strip()
    if not history_block:
        history_block = "(无历史交互)"
    if not m4_id:
        return jsonify({"error": "module4_session_id is required"}), 400

    s4 = get_module4_session(m4_id)
    if not s4:
        return jsonify({"error": "Module4 session not found"}), 404
    if not (s4.state == "confirmed" or force or "可以结束了" in user_input):
        return jsonify({"error": "Module4 not confirmed yet. Please confirm first."}), 400

    notes = load_notes()
    model_user_input = "\n\n".join(
        [
            "已确认的问题定义：",
            s4.definition,
            "",
            "Module 4 报告：",
            s4.report_md,
            "",
            "Function 5 历史交互（仅参考）：",
            history_block,
            "",
            "本轮用户输入：",
            user_input or "(无)",
            "",
            "交互区元数据：",
            f"tags: {notes.get('tags', [])}\nquotes: {notes.get('quotes', [])}\nhooks: {notes.get('hooks', [])}",
        ]
    )

    try:
        resp = asyncio.run(call_deepseek(system_prompt=_module5_system_prompt(user_id), user_input=model_user_input))
        out = extract_assistant_content(resp).strip()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not out:
        return jsonify({"error": "Empty output"}), 500

    s5 = new_module5_session(module4_session_id=s4.session_id, output_md=out)
    s5.state = "done"
    save_module5_session(s5)

    extracted = extract_tags_quotes_hooks(out)
    notes = merge_notes(notes, topic=notes.get("topic") or "", tags=extracted.tags, quotes=extracted.quotes, hooks=extracted.hooks)
    save_notes(notes)

    return jsonify({"session_id": s5.session_id, "module": "module5", "assistant": out, "state": s5.state})


@app.post("/ecm/module5/generate_stream")
def module5_generate_stream():
    """
    Streaming variant of Module5 generate.
    SSE: data=<delta>, event: final data=<json>
    """
    if not settings.deepseek_api_key:
        return jsonify({"error": "Missing DEEPSEEK_API_KEY. Create .env in ecm_backend and set it."}), 500

    body = request.get_json(silent=True) or {}
    m4_id = (body.get("module4_session_id") or "").strip()
    force = bool(body.get("force") or False)
    user_input = (body.get("user_input") or "").strip()
    user_id = (body.get("userId") or body.get("user_id") or "").strip()
    module5_history_raw = body.get("module5_history") or body.get("module5History") or body.get("history") or []

    module5_history: list[dict[str, str]] = []
    if isinstance(module5_history_raw, list):
        for x in module5_history_raw:
            if not isinstance(x, dict):
                continue
            role = _safe_str(x.get("role") or "").strip()
            content = _safe_str(x.get("content") or "")
            if role in ("user", "assistant") and content.strip():
                module5_history.append({"role": role, "content": content.strip()})

    history_tail = module5_history[-10:]
    history_block = "\n".join(
        f"{('用户' if m['role'] == 'user' else '导师')}: {m['content']}" for m in history_tail
    ).strip()
    if not history_block:
        history_block = "(无历史交互)"
    if not m4_id:
        return jsonify({"error": "module4_session_id is required"}), 400

    s4 = get_module4_session(m4_id)
    if not s4:
        return jsonify({"error": "Module4 session not found"}), 404
    if not (s4.state == "confirmed" or force or "可以结束了" in user_input):
        return jsonify({"error": "Module4 not confirmed yet. Please confirm first."}), 400

    notes = load_notes()
    model_user_input = "\n\n".join(
        [
            "已确认的问题定义：",
            s4.definition,
            "",
            "Module 4 报告：",
            s4.report_md,
            "",
            "Function 5 历史交互（仅参考）：",
            history_block,
            "",
            "本轮用户输入：",
            user_input or "(无)",
            "",
            "交互区元数据：",
            f"tags: {notes.get('tags', [])}\nquotes: {notes.get('quotes', [])}\nhooks: {notes.get('hooks', [])}",
        ]
    )

    sys_prompt = _module5_system_prompt(user_id)

    def gen():
        try:
            parts: list[str] = []
            for piece in stream_deepseek(system_prompt=sys_prompt, user_input=model_user_input):
                parts.append(piece)
                yield _sse(piece)
            out = "".join(parts).strip()
        except Exception as e:
            out = str(e)
            yield _sse(out)

        if not out:
            out = "Empty output"

        # Normalize markdown so Function 5 headings/bullets render correctly.
        out = _normalize_student_markdown(out)

        s5 = new_module5_session(module4_session_id=s4.session_id, output_md=out)
        s5.state = "done"
        save_module5_session(s5)

        extracted = extract_tags_quotes_hooks(out)
        notes2 = merge_notes(notes, topic=notes.get("topic") or "", tags=extracted.tags, quotes=extracted.quotes, hooks=extracted.hooks)
        save_notes(notes2)

        yield _sse(
            json.dumps({"session_id": s5.session_id, "module": "module5", "assistant": out, "state": s5.state}, ensure_ascii=False),
            event="final",
        )

    return Response(stream_with_context(gen()), mimetype="text/event-stream")


@app.post("/ecm/module5/generate_stream_from_report")
def module5_generate_stream_from_report():
    """
    Streaming variant of Module5 generate, but allows Module4 session_id to be missing.
    Request body:
      {
        module4Definition: string,   # optional, best-effort
        module4ReportMd: string,    # required (from student Function 4 chat content)
        force: optional bool,
        user_input: optional string,
        userId: string
      }
    """
    if not settings.deepseek_api_key:
        return jsonify({"error": "Missing DEEPSEEK_API_KEY. Create .env in ecm_backend and set it."}), 500

    body = request.get_json(silent=True) or {}
    module4_definition = _safe_str(body.get("module4Definition") or body.get("module1Definition") or "")
    module4_report_md = _safe_str(body.get("module4ReportMd") or body.get("module4Report") or "")
    force = bool(body.get("force") or False)
    user_input = _safe_str(body.get("user_input") or "")
    user_id = _safe_str(body.get("userId") or body.get("user_id") or "").strip()
    module5_history_raw = body.get("module5_history") or body.get("module5History") or body.get("history") or []

    module5_history: list[dict[str, str]] = []
    if isinstance(module5_history_raw, list):
        for x in module5_history_raw:
            if not isinstance(x, dict):
                continue
            role = _safe_str(x.get("role") or "").strip()
            content = _safe_str(x.get("content") or "")
            if role in ("user", "assistant") and content.strip():
                module5_history.append({"role": role, "content": content.strip()})

    history_tail = module5_history[-10:]
    history_block = "\n".join(
        f"{('用户' if m['role'] == 'user' else '导师')}: {m['content']}" for m in history_tail
    ).strip()
    if not history_block:
        history_block = "(无历史交互)"

    if not module4_report_md:
        return jsonify({"error": "module4ReportMd is required"}), 400
    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    notes = load_notes()
    model_user_input = "\n\n".join(
        [
            "已确认的问题定义：",
            module4_definition.strip(),
            "",
            "Module 4 报告：",
            module4_report_md.strip(),
            "",
            "Function 5 历史交互（仅参考）：",
            history_block,
            "",
            "本轮用户输入：",
            user_input or "(无)",
            "",
            "交互区元数据：",
            f"tags: {notes.get('tags', [])}\nquotes: {notes.get('quotes', [])}\nhooks: {notes.get('hooks', [])}",
        ]
    )

    sys_prompt = _module5_system_prompt(user_id)

    def gen():
        try:
            parts: list[str] = []
            for piece in stream_deepseek(system_prompt=sys_prompt, user_input=model_user_input):
                parts.append(piece)
                yield _sse(piece)
            out = "".join(parts).strip()
        except Exception as e:
            out = str(e)
            yield _sse(out)

        if not out:
            out = "Empty output"

        # Normalize markdown so Function 5 headings/bullets render correctly.
        out = _normalize_student_markdown(out)

        # Recreate Module4 session for traceability (because Module5 requires Module4 session_id).
        s4 = new_module4_session(definition=module4_definition or "", report_md=module4_report_md)
        s4.state = "confirmed"
        s4.history.append({"role": "assistant", "content": module4_report_md})
        save_module4_session(s4)

        s5 = new_module5_session(module4_session_id=s4.session_id, output_md=out)
        s5.state = "done"
        save_module5_session(s5)

        extracted = extract_tags_quotes_hooks(out)
        notes2 = merge_notes(notes, topic=notes.get("topic") or "", tags=extracted.tags, quotes=extracted.quotes, hooks=extracted.hooks)
        save_notes(notes2)

        yield _sse(
            json.dumps({"session_id": s5.session_id, "module": "module5", "assistant": out, "state": s5.state}, ensure_ascii=False),
            event="final",
        )

    return Response(stream_with_context(gen()), mimetype="text/event-stream")


def main() -> None:
    # NOTE: We intentionally use Flask's builtin server for local development.
    # In some environments, waitress may raise encoding errors when serving docx/binary payloads.
    # Flask's server is sufficient for this MVP and improves export stability.
    app.run(host="127.0.0.1", port=9000, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()

