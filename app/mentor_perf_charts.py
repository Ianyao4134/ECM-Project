"""
Matplotlib-based mentor performance visualizations (time-ordered student analytics).
Uses Agg backend; Chinese labels via common Windows fonts with fallbacks.
"""

from __future__ import annotations

import base64
import io
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colormaps
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.gridspec import GridSpec


def _zh_rc() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _flatten_and_order_events(analytics: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for mod, rows in analytics.items():
        for r in rows:
            if not isinstance(r, dict):
                continue
            t = int(r.get("updated_at") or 0)
            feats: dict[str, float] = {}
            m = r.get("metrics")
            if isinstance(m, dict):
                for k, v in m.items():
                    if isinstance(v, bool):
                        continue
                    if isinstance(v, (int, float)):
                        feats[f"{mod}.{k}"] = float(v)
            if mod == "f1":
                feats["__volume.history_bytes"] = float(r.get("history_payload_bytes") or 0)
            elif mod == "f2":
                feats["__volume.history_bytes"] = float(r.get("history_payload_bytes") or 0)
            elif mod == "f3":
                feats["__volume.note_chars"] = float(r.get("note_char_len") or 0)
                feats["__volume.cards_bytes"] = float(r.get("cards_payload_bytes") or 0)
            elif mod == "f4":
                feats["__volume.report_chars"] = float(r.get("report_char_len") or 0)
            elif mod == "f5":
                feats["__volume.review_chars"] = float(r.get("review_char_len") or 0)
                feats["__volume.final_note_chars"] = float(r.get("final_note_char_len") or 0)

            events.append(
                {
                    "ts_ms": t,
                    "module": mod,
                    "dialogue_id": str(r.get("dialogue_id") or ""),
                    "project_id": str(r.get("project_id") or ""),
                    "conversation_id": str(r.get("conversation_id") or ""),
                    "features": feats,
                }
            )

    if not events:
        return []

    first_seen: dict[str, int] = {}
    for e in events:
        did = e["dialogue_id"] or "__none"
        ts = e["ts_ms"]
        if did not in first_seen:
            first_seen[did] = ts
        else:
            first_seen[did] = min(first_seen[did], ts)
    dialogue_order = sorted(first_seen.keys(), key=lambda d: first_seen[d])
    rank = {d: i for i, d in enumerate(dialogue_order)}

    events.sort(
        key=lambda e: (
            rank.get(e["dialogue_id"] or "__none", 9999),
            e["ts_ms"],
            e["module"],
            e["conversation_id"],
        )
    )
    for i, e in enumerate(events, 1):
        e["seq"] = i
        e["dialogue_order"] = rank.get(e["dialogue_id"] or "__none", 0)
    return events


def _top_metric_keys(events: list[dict[str, Any]], max_keys: int = 18) -> list[str]:
    scores: dict[str, float] = {}
    for e in events:
        for k, v in e["features"].items():
            if k.startswith("__"):
                continue
            scores[k] = scores.get(k, 0.0) + abs(float(v))
    ranked = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return ranked[:max_keys]


_METRIC_KEY_TO_CN: dict[str, str] = {
    # F1 common
    "avg_ai_msg_length": "AI消息长度均值（字符）",
    "avg_user_msg_length": "学生消息长度均值（字符）",
    "ai_response_seconds_avg": "AI回应时长均值（秒）",
    "module_dwell_seconds": "模块停留时长均值（秒）",
    "turn_count": "对话轮次均值",
    "user_confirm_count": "确认次数均值",
    "user_copy_example_count": "复制/范例使用次数均值",
    "user_option_select_count": "选项选择次数均值",
    "user_question_count": "提问次数均值",
    "user_thinking_seconds_avg": "思考时长均值（秒）",
    "thinking_seconds_avg": "思考时长均值（秒）",

    # F3
    "avg_similarity": "卡片相似度均值",
    "avg_update_depth": "更新深度均值",
    "card_count": "卡片数量均值",
    "edit_rate": "编辑率",
    "edited_card_count": "已编辑卡片数量均值",
    "user_edit_count": "用户编辑次数均值",
    "star_rate": "标星率",
    "send_rate": "发送率",

    # F4
    "download_count": "下载次数",
    "report_modification_count": "报告修改次数",

    # F5
    "click_count": "点击次数",
    "new_count": "新增次数",
    "note_char_count": "笔记字符数",
    "note_edit_count": "笔记编辑次数",
}


def _feature_key_to_cn(feature_key: str) -> str:
    """
    Convert internal feature keys (e.g. 'f1.ai_response_seconds_avg') to human-readable Chinese labels.
    """
    if not feature_key or not isinstance(feature_key, str):
        return "指标"
    if "." in feature_key:
        mod, metric = feature_key.split(".", 1)
    else:
        mod, metric = "", feature_key
    cn = _METRIC_KEY_TO_CN.get(metric)
    if cn:
        return f"{mod.upper()} · {cn}" if mod else cn
    # Fallback: avoid leaking raw variable names.
    return f"{mod.upper()} · 未知指标" if mod else "未知指标"


def _matrix_for_heatmap(events: list[dict[str, Any]], keys: list[str]) -> tuple[np.ndarray, list[str]]:
    if not events or not keys:
        return np.zeros((0, 0)), []
    raw = np.zeros((len(keys), len(events)), dtype=float)
    for j, e in enumerate(events):
        for i, k in enumerate(keys):
            raw[i, j] = float(e["features"].get(k, np.nan))
    out = raw.copy()
    for i in range(out.shape[0]):
        row = out[i, :]
        mask = np.isfinite(row)
        if not np.any(mask):
            continue
        lo, hi = np.nanmin(row[mask]), np.nanmax(row[mask])
        if hi > lo:
            out[i, mask] = (row[mask] - lo) / (hi - lo)
        else:
            out[i, mask] = 0.5
    out = np.nan_to_num(out, nan=0.0)
    return out, keys


def build_timeline_events_payload(analytics: dict[str, list[dict[str, Any]]], *, max_events: int = 400) -> dict[str, Any]:
    ev = _flatten_and_order_events(analytics)
    total = len(ev)
    ev_list = ev[: max(0, int(max_events))]
    return {
        "event_count": total,
        "events_truncated": total > len(ev_list),
        "dialogue_order": list(dict.fromkeys(e["dialogue_id"] or "(空)" for e in ev)),
        "events": [
            {
                "seq": e["seq"],
                "ts_ms": e["ts_ms"],
                "module": e["module"],
                "dialogue_id": e["dialogue_id"],
                "project_id": e["project_id"],
                "conversation_id": e["conversation_id"][:12] + "…" if len(e["conversation_id"]) > 14 else e["conversation_id"],
            }
            for e in ev_list
        ],
    }


def build_deepseek_charts_context(
    analytics: dict[str, list[dict[str, Any]]],
    *,
    max_events: int = 160,
    max_metric_keys: int = 12,
) -> dict[str, Any]:
    """
    Compact, chart-ready context for DeepSeek time-series解读.
    只提供结构化数值序列，不包含任何图片 base64。
    """
    ev = _flatten_and_order_events(analytics)
    total = len(ev)
    ev_list = ev[: max(0, int(max_events))]

    top_keys = _top_metric_keys(ev, max_keys=int(max_metric_keys))
    series: list[dict[str, Any]] = []
    for e in ev_list:
        values: dict[str, Any] = {}
        for k in top_keys:
            v = e["features"].get(k)
            if v is None:
                continue
            try:
                fv = float(v)
                values[k] = fv if np.isfinite(fv) else None
            except Exception:
                values[k] = None
        series.append(
            {
                "seq": e.get("seq"),
                "ts_ms": e.get("ts_ms"),
                "module": e.get("module"),
                "dialogue_id": e.get("dialogue_id"),
                "project_id": e.get("project_id"),
                "values": values,
            }
        )

    return {
        "events_total": total,
        "events_included": len(ev_list),
        "events_truncated": total > len(ev_list),
        "timeline": build_timeline_events_payload(analytics, max_events=max_events),
        "top_metric_keys": top_keys,
        "time_series": series,
    }


def render_performance_figures_png(
    analytics: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """
    Returns list of { title, mime, data_base64, width_px, height_px }.
    """
    _zh_rc()
    events = _flatten_and_order_events(analytics)
    figures: list[dict[str, Any]] = []

    if not events:
        fig, ax = plt.subplots(figsize=(10, 4), dpi=120)
        fig.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#ffffff")
        ax.text(0.5, 0.5, "暂无 analytics 记录", ha="center", va="center", color="#111111", fontsize=14)
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.patch.get_facecolor())
        plt.close(fig)
        b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
        figures.append(
            {
                "title": "提示",
                "mime": "image/png",
                "data_base64": b64,
                "width_px": 1200,
                "height_px": 480,
            }
        )
        return figures

    # --- Figure 1: timeline + module strip + volume stack ---
    fig = plt.figure(figsize=(14, 10), dpi=110, facecolor="#ffffff")
    gs = GridSpec(4, 2, figure=fig, height_ratios=[1.1, 1.0, 1.15, 0.9], hspace=0.35, wspace=0.22)

    mod_to_y = {"f1": 0, "f2": 1, "f3": 2, "f4": 3, "f5": 4}
    colors_mod = {
        "f1": "#ff6b9d",
        "f2": "#c084fc",
        "f3": "#67e8f9",
        "f4": "#86efac",
        "f5": "#fcd34d",
    }

    xs = [datetime.fromtimestamp(e["ts_ms"] / 1000.0, tz=timezone.utc) for e in events]
    ys = [mod_to_y[e["module"]] + 0.04 * ((e["seq"] + mod_to_y[e["module"]]) % 5) for e in events]
    sz = [40 + min(120, e["seq"]) for e in events]
    cs = [colors_mod.get(e["module"], "#888") for e in events]

    ax1 = fig.add_subplot(gs[0, :])
    ax1.set_facecolor("#ffffff")
    ax1.scatter(xs, ys, s=sz, c=cs, alpha=0.85, edgecolors="#00000022", linewidths=0.6)
    ax1.set_yticks(range(5))
    ax1.set_yticklabels(["F1", "F2", "F3", "F4", "F5"])
    ax1.set_xlabel("时间（UTC）", color="#333333")
    ax1.set_title("时间序列 · 按对话先后排序的模块活动（点大小≈事件序号）", color="#222222", fontsize=12)
    ax1.tick_params(colors="#444444")
    ax1.grid(True, alpha=0.15, color="#00000012")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=22, ha="right")
    for spine in ax1.spines.values():
        spine.set_color("#dddddd")

    for i, e in enumerate(events):
        if i == 0 or (e["dialogue_id"] or "") != (events[i - 1]["dialogue_id"] or ""):
            t = mdates.date2num(xs[i])
            ax1.axvline(t, color="#00000010", linewidth=1, linestyle="--")

    # --- cumulative volumes ---
    ax2 = fig.add_subplot(gs[1, :])
    ax2.set_facecolor("#ffffff")
    seq = np.arange(1, len(events) + 1)
    vol_keys = [
        ("__volume.history_bytes", "F1/F2 对话载荷 (bytes)", "#ff6b9d"),
        ("__volume.note_chars", "F3 笔记字符", "#67e8f9"),
        ("__volume.report_chars", "F4 报告字符", "#86efac"),
        ("__volume.review_chars", "F5 回顾字符", "#fcd34d"),
    ]
    for vk, label, c in vol_keys:
        series = []
        acc = 0.0
        for e in events:
            v = e["features"].get(vk)
            if v is not None and np.isfinite(v):
                acc += float(v)
            series.append(acc)
        if max(series, default=0) <= 0:
            continue
        ax2.plot(seq, series, label=label, color=c, linewidth=2.1, alpha=0.9)
    ax2.set_xlabel("事件序号（按对话与时间排序）", color="#333333")
    ax2.set_ylabel("累积体量", color="#333333")
    ax2.set_title("内容体量 · 随事件推进的累积曲线", color="#222222", fontsize=12)
    ax2.legend(loc="upper left", fontsize=8, framealpha=0.35, facecolor="#ffffff")
    ax2.tick_params(colors="#444444")
    ax2.grid(True, alpha=0.15, color="#00000012")

    # --- heatmap ---
    keys = _top_metric_keys(events, max_keys=16)
    mat, klabels = _matrix_for_heatmap(events, keys)
    ax3 = fig.add_subplot(gs[2, :])
    ax3.set_facecolor("#ffffff")
    if mat.size > 0:
        cmap = LinearSegmentedColormap.from_list("ecm", ["#1e1b4b", "#6366f1", "#fbbf24", "#f472b6"])
        im = ax3.imshow(mat, aspect="auto", cmap=cmap, interpolation="nearest")
        ax3.set_yticks(range(len(klabels)))
        ax3.set_yticklabels([_feature_key_to_cn(k)[:28] for k in klabels], fontsize=7, color="#444444")
        step = max(1, len(events) // 14)
        tick_idx = list(range(0, len(events), step))
        ax3.set_xticks(tick_idx)
        ax3.set_xticklabels([str(events[i]["seq"]) for i in tick_idx], fontsize=7)
        ax3.set_xlabel("事件序号", color="#333333")
        ax3.set_title("多维度指标热力图（按列：时间顺序；行内已按事件 min-max 归一）", color="#222222", fontsize=12)
        plt.colorbar(im, ax=ax3, fraction=0.02, pad=0.02)
    else:
        ax3.text(0.5, 0.5, "无足够数值型 metrics", ha="center", va="center", color="#888888", transform=ax3.transAxes)

    # --- bar: events per dialogue in order ---
    ax4 = fig.add_subplot(gs[3, :])
    ax4.set_facecolor("#ffffff")

    counts: OrderedDict[str, int] = OrderedDict()
    order_d: list[str] = []
    for e in events:
        d = e["dialogue_id"] or "(未标注)"
        if d not in counts:
            counts[d] = 0
            order_d.append(d)
        counts[d] += 1
    xb = np.arange(len(order_d))
    bars = ax4.bar(xb, [counts[d] for d in order_d], color="#818cf8", edgecolor="#c7d2fe", alpha=0.9)
    ax4.set_xticks(xb)
    ax4.set_xticklabels([d[:10] + "…" if len(d) > 12 else d for d in order_d], rotation=35, ha="right", fontsize=8, color="#444444")
    ax4.set_ylabel("记录条数", color="#333333")
    ax4.set_title("各对话（按首次出现排序）analytics 条数分布", color="#222222", fontsize=11)
    ax4.tick_params(colors="#444444")
    ax4.grid(True, axis="y", alpha=0.15, color="#00000012")
    for b, d in zip(bars, order_d):
        ax4.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.1, str(counts[d]), ha="center", fontsize=8, color="#222222")

    fig.suptitle("ECM 学生全量表现 · 时间序列可视化", color="#111111", fontsize=14, fontweight="bold", y=0.995)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.patch.get_facecolor(), edgecolor="none")
    plt.close(fig)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    figures.append(
        {
            "title": "综合看板（时间轴 / 累积体量 / 热力图 / 对话分布）",
            "mime": "image/png",
            "data_base64": b64,
            "width_px": 1540,
            "height_px": 1100,
        }
    )

    # --- Figure 2: per-module metric lines (sparse) ---
    fig2, axes = plt.subplots(5, 1, figsize=(14, 12), dpi=100, facecolor="#ffffff", sharex=True)
    mods = ["f1", "f2", "f3", "f4", "f5"]
    for ax, mod in zip(axes, mods):
        ax.set_facecolor("#ffffff")
        sub_ev = [e for e in events if e["module"] == mod]
        if not sub_ev:
            ax.text(0.5, 0.5, f"{mod.upper()} 无记录", ha="center", va="center", color="#666", transform=ax.transAxes)
            ax.axis("off")
            continue
        sub_keys = _top_metric_keys(sub_ev, max_keys=5)
        seq_m = [e["seq"] for e in sub_ev]
        if not sub_keys:
            ax.text(0.5, 0.5, f"{mod.upper()} 无数值型 metrics", ha="center", va="center", color="#666", transform=ax.transAxes)
            ax.axis("off")
            continue
        cmap2 = colormaps["tab10"]
        for ki, key in enumerate(sub_keys):
            vals = [e["features"].get(key, np.nan) for e in sub_ev]
            if not any(np.isfinite(v) for v in vals):
                continue
            ax.plot(
                seq_m,
                vals,
                marker="o",
                markersize=3,
                label=_feature_key_to_cn(key)[:20],
                color=cmap2(ki % 10),
                alpha=0.9,
            )
        ax.set_ylabel(mod.upper(), color=colors_mod[mod], fontweight="bold")
        ax.grid(True, alpha=0.15, color="#00000012")
        ax.legend(loc="upper right", fontsize=7, ncol=2, framealpha=0.3)
        ax.tick_params(colors="#444444")
    axes[-1].set_xlabel("全局事件序号（与其它图对齐）", color="#333333")
    fig2.suptitle("分模块 · 数值型 metrics 随事件序号变化", color="#222222", fontsize=13)
    buf2 = io.BytesIO()
    fig2.savefig(buf2, format="png", bbox_inches="tight", facecolor=fig2.patch.get_facecolor())
    plt.close(fig2)
    figures.append(
        {
            "title": "分模块指标曲线",
            "mime": "image/png",
            "data_base64": base64.standard_b64encode(buf2.getvalue()).decode("ascii"),
            "width_px": 1540,
            "height_px": 1320,
        }
    )

    return figures
