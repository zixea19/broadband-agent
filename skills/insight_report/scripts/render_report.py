#!/usr/bin/env python3
"""报告渲染脚本 — 将 InsightAgent 的执行产物渲染为 Markdown 报告。

作为 agno Skill 脚本被调用。stdout 即最终产物，Agent 必须原样输出。

自动识别两种上下文形态：
- **多阶段形态**（新）：含 `phases` 键 → 使用 `multi_phase_report.md.j2`
- **归因形态**（旧）：含 `analysis` 键 → 使用 `report.md.j2`（向后兼容）
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment

# Windows 兼容：强制 stdout 使用 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_REFERENCES_DIR = Path(__file__).resolve().parents[1] / "references"


def _gbk_safe(text: str) -> str:
    """Strip characters that cannot be encoded in GBK (primarily emoji).

    agno captures subprocess stdout with the system locale encoding (GBK on Chinese
    Windows).  Chinese text and most punctuation are GBK-compatible; emoji and other
    supplementary-plane characters are not.  Removing them prevents the
    UnicodeDecodeError agno raises when it tries to decode our stdout bytes.
    SKILL.md already prohibits emoji in context fields — this enforces it at code level.
    """
    result: list[str] = []
    for ch in text:
        try:
            ch.encode("gbk")
            result.append(ch)
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass  # silently drop unencodable chars (emoji etc.)
    return "".join(result)


def _safe_parse_json(raw: str) -> dict:
    """带修复的 JSON 解析：先直接解析，失败则尝试修复常见 shell 转义损坏后重试。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    stripped = raw.strip()
    if stripped.startswith("'") and stripped.endswith("'"):
        stripped = stripped[1:-1]
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    repaired = re.sub(r"(?<=[{,])\s*([a-zA-Z_]\w*)\s*:", r' "\1":', raw)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass
    try:
        from json_repair import repair_json

        return json.loads(repair_json(raw, return_objects=False))
    except (ImportError, Exception):
        pass
    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                return json.loads(stdin_data)
        except Exception:
            pass
    return json.loads(raw)


def _inject_chart_placeholders(ctx: Dict[str, Any]) -> None:
    """对 chart_configs 非空的步骤，自动在 description 末尾追加 [CHART:p{phase_id}s{step_id}]。

    LLM 生成占位符不稳定（多 phase 时容易遗漏），由脚本统一处理更可靠。
    若 description 末尾已含正确占位符则跳过（幂等）。
    """
    for phase in ctx.get("phases") or []:
        phase_id = phase.get("phase_id", 0)
        for step in phase.get("steps") or []:
            if not step.get("chart_configs"):
                continue
            step_id = step.get("step_id", 0)
            placeholder = f"[CHART:p{phase_id}s{step_id}]"
            desc = step.get("description") or ""
            if isinstance(desc, dict):
                # description 是 dict 时取 summary 字段插入占位符
                summary = desc.get("summary", "")
                if placeholder not in summary:
                    desc["summary"] = summary + f"\n\n{placeholder}"
            else:
                if placeholder not in str(desc):
                    step["description"] = str(desc) + f"\n\n{placeholder}"


def render(context_json: str) -> str:
    """渲染 Markdown 报告。

    Args:
        context_json: 上下文 JSON 字符串，支持两种形态（见模块 docstring）。
    """
    try:
        ctx: Dict[str, Any] = (
            _safe_parse_json(context_json) if isinstance(context_json, str) else context_json
        )
    except json.JSONDecodeError as exc:
        return f"渲染失败: 无效的上下文 JSON — {exc}"

    ctx.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    _inject_chart_placeholders(ctx)

    template_name = _pick_template(ctx)
    template_path = _REFERENCES_DIR / template_name

    try:
        # Read template explicitly as UTF-8 — avoids FileSystemLoader relying on
        # the system locale encoding (GBK on Chinese Windows).
        with open(template_path, encoding="utf-8") as fh:
            template_source = fh.read()
        env = Environment(keep_trailing_newline=True)
        rendered = env.from_string(template_source).render(**ctx)
        # Strip non-GBK characters (emoji etc.) so agno's GBK stdout decoder doesn't crash.
        return _gbk_safe(rendered)
    except Exception as exc:
        return f"渲染失败: {exc}"


def _pick_template(ctx: Dict[str, Any]) -> str:
    """选择模板。phases 优先（新多阶段），否则回退 report.md.j2（旧归因）。"""
    if ctx.get("phases"):
        return "multi_phase_report.md.j2"
    return "report.md.j2"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(render(sys.argv[1]))
    else:
        print(render("{}"))
