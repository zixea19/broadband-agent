"""上下文增长检查器 — 把 llm_prompt trace 变成可读的"每次 LLM 调用看到了什么"视图。

用法:
    # 最新 session 的 insight agent（最常用）
    uv run python scripts/inspect_context.py

    # 指定 session hash（前缀即可）
    uv run python scripts/inspect_context.py --session abc123

    # 指定 agent（默认 insight）
    uv run python scripts/inspect_context.py --agent orchestrator

    # 查看指定日期的 trace 文件
    uv run python scripts/inspect_context.py --date 2024-01-15

    # 显示每条消息的完整内容（不截断）
    uv run python scripts/inspect_context.py --full

    # 只看某次 LLM 调用的完整上下文（如第 3 次）
    uv run python scripts/inspect_context.py --call 3
"""

import argparse
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TRACE_DIR = _ROOT / "data" / "logs" / "trace"

_ROLE_ICON = {
    "system": "⚙",
    "user": "👤",
    "assistant": "🤖",
    "tool": "🔧",
    "unknown": "?",
}

_COLORS = {
    "new": "\033[92m",      # 绿色：新增消息
    "carried": "\033[90m",  # 灰色：延续消息
    "header": "\033[96m",   # 青色：标题
    "warn": "\033[93m",     # 黄色：警告
    "reset": "\033[0m",
    "bold": "\033[1m",
}


def _c(text: str, *keys: str) -> str:
    """Apply ANSI color codes."""
    if not sys.stdout.isatty():
        return text
    prefix = "".join(_COLORS[k] for k in keys)
    return f"{prefix}{text}{_COLORS['reset']}"


def _estimate_tokens(text: str) -> int:
    """粗略 token 估算：中文约 1.5 字符/token，英文约 4 字符/token，取混合估算。"""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if "一" <= c <= "鿿")
    other_chars = len(text) - chinese_chars
    return max(1, int(chinese_chars / 1.5 + other_chars / 4))


def _extract_content_str(content: str | list | dict) -> str:
    """把各种格式的 content 统一成可读字符串。"""
    if isinstance(content, list):
        # OpenAI 多块格式: [{"type": "text", "text": "..."}, {"type": "tool_result", ...}]
        parts = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
                continue
            btype = block.get("type", "")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype in ("tool_result", "tool_use"):
                name = block.get("name", block.get("tool_use_id", ""))
                inner = block.get("content") or block.get("input") or ""
                if isinstance(inner, list):
                    inner = " ".join(
                        b.get("text", str(b)) if isinstance(b, dict) else str(b)
                        for b in inner
                    )
                parts.append(f"[{btype}:{name}] {str(inner)[:200]}")
            else:
                parts.append(json.dumps(block, ensure_ascii=False)[:200])
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _parse_content(raw: str | list | dict) -> tuple[str, str]:
    """返回 (label, preview) 两部分，label 用于识别消息类型。

    label 示例: "get_skill_instructions:insight_decompose", "event:plan", "insight.md"
    """
    text = _extract_content_str(raw)

    # 尝试 JSON 解析（tool result 通常是 JSON 字符串）
    parsed = None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(raw, (dict, list)):
        parsed = raw

    # 从解析结果中提取 skill 名
    if isinstance(parsed, dict):
        skill = parsed.get("skill_name") or parsed.get("skill") or ""
        script = parsed.get("script_path", "")
        op = parsed.get("op", "")
        if skill and script:
            label = f"get_skill_script:{skill}/{Path(script).name}"
        elif skill and op:
            label = f"{op}:{skill}"
        elif skill:
            label = f"skill:{skill}"
        else:
            label = ""
    elif isinstance(raw, list):
        # 多块消息：找 tool_use/tool_result
        names = []
        for block in raw:
            if isinstance(block, dict):
                n = block.get("name") or block.get("tool_use_id", "")
                if n:
                    names.append(n)
        label = ", ".join(names) if names else ""
    else:
        label = ""

    # 从文本中提取事件标记
    event_match = re.search(r"<!--event:(\w+)-->", text)
    if event_match and not label:
        label = f"event:{event_match.group(1)}"

    # system prompt 识别
    if not label and len(text) > 500 and ("skill" in text.lower() or "phase" in text.lower()):
        first_line = text.split("\n")[0].strip()
        label = first_line[:60] if first_line else "system_prompt"

    preview = text.replace("\n", " ").strip()
    return label, preview


def _format_message(msg: dict, is_new: bool, show_full: bool, max_preview: int = 120) -> str:
    role = msg.get("role", "unknown")
    raw_content = msg.get("content", "")

    # content 可能是 JSON 字符串（tracer 序列化结果）
    try:
        content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    except (json.JSONDecodeError, TypeError):
        content = raw_content

    label, preview = _parse_content(content)
    tokens = _estimate_tokens(_extract_content_str(content))

    icon = _ROLE_ICON.get(role, "?")
    role_str = f"{icon} [{role}]"

    label_str = f"  {label}" if label else ""
    tok_str = _c(f"(~{tokens:,} tok)", "warn" if tokens > 3000 else "carried")

    if show_full:
        full_text = _extract_content_str(content)
        body = f"\n{full_text}"
    else:
        truncated = preview[:max_preview] + ("…" if len(preview) > max_preview else "")
        body = f'  "{truncated}"'

    line = f"  {role_str}{label_str}  {tok_str}{body}"

    if is_new:
        return _c(line + "  ← NEW", "new")
    return _c(line, "carried")


def _load_trace_file(date: str | None = None) -> list[dict]:
    """加载指定日期（或最新）的 JSONL trace 文件。"""
    if not _TRACE_DIR.exists():
        return []

    if date:
        path = _TRACE_DIR / f"{date}.jsonl"
        if not path.exists():
            print(_c(f"找不到 trace 文件: {path}", "warn"))
            return []
        files = [path]
    else:
        files = sorted(_TRACE_DIR.glob("*.jsonl"), reverse=True)
        if not files:
            return []
        files = files[:1]  # 最新一天

    records = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def _filter_records(
    records: list[dict],
    session_prefix: str | None,
    agent_filter: str,
) -> list[dict]:
    """筛选 llm_prompt 事件，按 session + agent 过滤。"""
    prompts = [r for r in records if r.get("event") == "llm_prompt"]
    if agent_filter:
        prompts = [r for r in prompts if agent_filter.lower() in (r.get("agent", "")).lower()]

    if session_prefix:
        prompts = [r for r in prompts if r.get("session", "").startswith(session_prefix)]
    elif prompts:
        # 默认取最新 session
        latest_session = prompts[-1].get("session", "")
        prompts = [r for r in prompts if r.get("session") == latest_session]

    return prompts


def _get_available_sessions(records: list[dict], agent_filter: str) -> list[str]:
    prompts = [r for r in records if r.get("event") == "llm_prompt"]
    if agent_filter:
        prompts = [r for r in prompts if agent_filter.lower() in (r.get("agent", "")).lower()]
    seen: dict[str, int] = {}
    for r in prompts:
        s = r.get("session", "")
        seen[s] = seen.get(s, 0) + 1
    return [f"{s}  ({n} calls)" for s, n in seen.items()]


def inspect(
    session_prefix: str | None = None,
    agent_filter: str = "insight",
    date: str | None = None,
    show_full: bool = False,
    focus_call: int | None = None,
) -> None:
    records = _load_trace_file(date)
    if not records:
        print(_c("未找到 trace 文件。先运行一次 InsightAgent 再来检查。", "warn"))
        print(f"  期望路径: {_TRACE_DIR}/<date>.jsonl")
        return

    prompts = _filter_records(records, session_prefix, agent_filter)
    if not prompts:
        available = _get_available_sessions(records, "")
        print(_c(f"没有找到 agent='{agent_filter}' 的 llm_prompt 事件。", "warn"))
        if available:
            print("  当前文件中的 sessions：")
            for s in available:
                print(f"    {s}")
        return

    session_hash = prompts[0].get("session", "unknown")
    agent_name = prompts[0].get("agent", agent_filter)

    bar = "━" * 72
    print(_c(f"\n{bar}", "header"))
    print(_c(
        f"  Session: {session_hash[:16]}…  |  Agent: {agent_name}  |  {len(prompts)} LLM calls",
        "header", "bold"
    ))
    print(_c(f"{bar}\n", "header"))

    prev_count = 0

    for call_idx, record in enumerate(prompts, start=1):
        if focus_call is not None and call_idx != focus_call:
            prev_count = len(record.get("payload", {}).get("messages", []))
            continue

        ts = record.get("ts", "")[:19].replace("T", " ")
        payload = record.get("payload", {})
        messages = payload.get("messages", [])
        msg_count = len(messages)
        total_tokens = sum(
            _estimate_tokens(
                _extract_content_str(
                    json.loads(m.get("content", ""))
                    if isinstance(m.get("content"), str)
                    else m.get("content", "")
                )
            )
            for m in messages
        )
        new_count = msg_count - prev_count
        delta_str = f"  {_c(f'+{new_count} new', 'new')}" if new_count > 0 and call_idx > 1 else ""

        print(_c(f"Call #{call_idx}", "bold") + f"  ·  {ts}  ·  {msg_count} msgs  ·  ~{total_tokens:,} tok{delta_str}")

        for i, msg in enumerate(messages):
            is_new = i >= prev_count
            print(_format_message(msg, is_new=is_new, show_full=show_full))

        print()
        prev_count = msg_count

    if focus_call is None:
        # 汇总
        all_tokens = []
        p = 0
        for r in prompts:
            msgs = r.get("payload", {}).get("messages", [])
            total = sum(
                _estimate_tokens(
                    _extract_content_str(
                        json.loads(m.get("content", ""))
                        if isinstance(m.get("content"), str)
                        else m.get("content", "")
                    )
                )
                for m in msgs
            )
            all_tokens.append(total)
            p = len(msgs)

        print(_c(bar, "header"))
        print(f"  Token 增长: {' → '.join(f'{t:,}' for t in all_tokens)}")
        if len(all_tokens) > 1:
            growth = all_tokens[-1] - all_tokens[0]
            print(f"  总增量: ~{growth:,} tok  (首次 → 末次)")
        print(_c(bar, "header"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="检查每次 LLM 调用的 context 增长情况",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--session", "-s", default=None, help="session hash 前缀（不填则取最新）")
    parser.add_argument("--agent", "-a", default="insight", help="agent 名称过滤（默认 insight）")
    parser.add_argument("--date", "-d", default=None, help="trace 文件日期，如 2024-01-15")
    parser.add_argument("--full", "-f", action="store_true", help="显示每条消息的完整内容")
    parser.add_argument("--call", "-c", type=int, default=None, help="只显示第 N 次 LLM 调用的完整上下文")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用的 session")
    args = parser.parse_args()

    if args.list:
        records = _load_trace_file(args.date)
        sessions = _get_available_sessions(records, args.agent)
        print(f"可用 sessions (agent={args.agent or '全部'}):")
        for s in sessions:
            print(f"  {s}")
        return

    inspect(
        session_prefix=args.session,
        agent_filter=args.agent,
        date=args.date,
        show_full=args.full,
        focus_call=args.call,
    )


if __name__ == "__main__":
    main()
