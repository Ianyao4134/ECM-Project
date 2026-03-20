from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .deepseek import call_deepseek, extract_assistant_content
from .parsing import extract_tags_quotes_hooks
from .prompts import build_system_prompt, load_prompt
from .notes_store import load_notes, merge_notes, save_notes


@dataclass(frozen=True)
class StageResult:
    state: str
    system_prompt_name: str
    user_input: str
    output: str
    extracted: dict[str, list[str]]


async def run_ecm(topic: str | None, question: str) -> dict[str, Any]:
    """
    Run the ECM state machine end-to-end and persist extracted notes.
    """
    module0 = load_prompt("module0_.txt")
    p1 = load_prompt("module1_steps.txt")
    p2 = load_prompt("module2_steps.txt")
    p3 = load_prompt("module3_Summary.txt")
    p4 = load_prompt("module4_summary.txt")
    p5 = load_prompt("module5_inspiration.txt")

    stages: list[StageResult] = []

    async def _run_state(state: str, prompt_name: str, system_prompt: str, user_input: str) -> StageResult:
        resp = await call_deepseek(system_prompt=system_prompt, user_input=user_input)
        out = extract_assistant_content(resp)
        extracted = extract_tags_quotes_hooks(out)
        return StageResult(
            state=state,
            system_prompt_name=prompt_name,
            user_input=user_input,
            output=out,
            extracted={"tags": extracted.tags, "quotes": extracted.quotes, "hooks": extracted.hooks},
        )

    # Function 1: define_problem
    s1_sys = build_system_prompt(module0, p1)
    s1_user = f"主题：{topic or ''}\n用户问题：{question}".strip()
    s1 = await _run_state("define_problem", "module1_steps.txt", s1_sys, s1_user)
    stages.append(s1)

    # Function 2: explore_step1..5 (each step uses same module2 prompt + rolling context)
    explore_context = s1.output
    for i in range(1, 6):
        state = f"explore_step{i}"
        s2_sys = build_system_prompt(module0, p2)
        s2_user = (
            f"主题：{topic or ''}\n"
            f"用户问题：{question}\n\n"
            f"上一步输出（问题定义/上下文）：\n{explore_context}\n\n"
            f"请输出 {state}。"
        )
        step = await _run_state(state, "module2_steps.txt", s2_sys, s2_user)
        stages.append(step)
        explore_context = step.output

    # Function 3: Summary of Function3 (summarize Function 2)
    f2_all = "\n\n".join([s.output for s in stages if s.state.startswith("explore_step")])
    s3_sys = build_system_prompt(module0, p3)
    s3_user = f"主题：{topic or ''}\n用户问题：{question}\n\n以下是 Function 2 的全部输出：\n{f2_all}"
    s3 = await _run_state("function3_summary", "module3_Summary.txt", s3_sys, s3_user)
    stages.append(s3)

    # Function 4: Summary
    s4_sys = build_system_prompt(module0, p4)
    s4_user = (
        f"主题：{topic or ''}\n用户问题：{question}\n\n"
        f"请基于以下内容总结：\n\n【Function 3 输出】\n{s3.output}\n"
    )
    s4 = await _run_state("summary", "module4_summary.txt", s4_sys, s4_user)
    stages.append(s4)

    # Function 5: inspiration
    s5_sys = build_system_prompt(module0, p5)
    s5_user = (
        f"主题：{topic or ''}\n用户问题：{question}\n\n"
        f"请基于以下内容给出灵感：\n\n【Function 4 输出】\n{s4.output}\n"
    )
    s5 = await _run_state("inspiration", "module5_inspiration.txt", s5_sys, s5_user)
    stages.append(s5)

    # Persist extracted notes (aggregate all stages)
    all_tags: list[str] = []
    all_quotes: list[str] = []
    all_hooks: list[str] = []
    for s in stages:
        all_tags.extend(s.extracted.get("tags", []))
        all_quotes.extend(s.extracted.get("quotes", []))
        all_hooks.extend(s.extracted.get("hooks", []))

    notes = load_notes()
    notes = merge_notes(notes, topic=topic or question, tags=all_tags, quotes=all_quotes, hooks=all_hooks)
    save_notes(notes)

    return {
        "topic": topic or "",
        "question": question,
        "stages": [
            {
                "state": s.state,
                "system_prompt": s.system_prompt_name,
                "user_input": s.user_input,
                "output": s.output,
                "extracted": s.extracted,
            }
            for s in stages
        ],
        "notes": notes,
    }

