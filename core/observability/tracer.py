"""业务追踪层 — 订阅 agno 事件流，落到 SQLite + JSONL。

写入失败绝不影响主流程。

每条 JSONL 记录结构:
    {"ts": "...", "session": "...", "agent": "insight|orchestrator|...",
     "is_leader": true/false, "event": "...", "payload": {...}}
并行 SubAgent 通过 agent 字段隔离，主 agent 通过 is_leader=true 区分。
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from core.observability.db import db

_TRACE_DIR = Path(__file__).resolve().parents[2] / "data" / "logs" / "trace"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_jsonl(
    event_type: str,
    session_hash: str,
    payload: Any,
    *,
    agent: str = "",
    is_leader: bool = False,
) -> None:
    """追加一行到当天的 JSONL 文件。

    Args:
        event_type: 事件类型
        session_hash: 会话标识
        payload: 事件载荷
        agent: 产生该事件的 agent 名称（如 "insight"、"orchestrator"）
        is_leader: 是否来自 Team leader
    """
    try:
        _TRACE_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = _TRACE_DIR / f"{today}.jsonl"
        line = json.dumps(
            {
                "ts": _now_iso(),
                "session": session_hash,
                "agent": agent,
                "is_leader": is_leader,
                "event": event_type,
                "payload": payload,
            },
            ensure_ascii=False,
            default=str,
        )
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        logger.warning(f"JSONL write failed: {event_type}")


class Tracer:
    """会话级 Tracer — 绑定到一个 session_hash。

    所有 trace 方法接受 agent / is_leader 参数，用于区分事件来源。
    并行 SubAgent 通过 agent 字段天然隔离。
    """

    def __init__(self, session_hash: str, db_session_id: Optional[int] = None):
        self.session_hash = session_hash
        self.db_session_id = db_session_id

    def trace(
        self,
        event_type: str,
        payload: Any = None,
        *,
        agent: str = "",
        is_leader: bool = False,
    ) -> None:
        """写入一条 trace 事件（SQLite + JSONL 双写）。"""
        try:
            if self.db_session_id is not None:
                # SQLite traces 表存储 agent 信息到 payload 中
                enriched = payload if isinstance(payload, dict) else {"data": payload}
                enriched = {**enriched, "_agent": agent, "_is_leader": is_leader}
                db.insert_trace(self.db_session_id, self.session_hash, event_type, enriched)
            _write_jsonl(event_type, self.session_hash, payload, agent=agent, is_leader=is_leader)
        except Exception:
            logger.warning(f"trace write failed: {event_type}")

    # ─── 用户请求/最终回复 ────────────────────────────────────────────

    def request(self, user_input: str) -> None:
        self.trace("request", {"input": user_input})

    def response(self, content: str) -> None:
        self.trace("response", {"content": content}, agent="orchestrator", is_leader=True)

    # ─── LLM 调用 (由 inject_prompt_tracer 触发) ─────────────────────

    def llm_prompt(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        tool_choice: Any = None,
        agent_name: str = "",
    ) -> None:
        """记录发送给 LLM 的完整请求（messages + tools 定义 + tool_choice）。

        Args:
            messages: 发送给 LLM 的消息列表
            tools: 可用工具定义
            tool_choice: 工具选择策略
            agent_name: 发出该 LLM 调用的 agent 名称
        """
        serialized = []
        for m in messages:
            try:
                role = getattr(m, "role", "unknown")
                content = getattr(m, "content", "")
                if isinstance(content, str):
                    try:
                        parsed = json.loads(content)
                        content = json.dumps(parsed, ensure_ascii=False)
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif isinstance(content, list):
                    content = json.dumps(content, ensure_ascii=False, default=str)
                serialized.append({"role": str(role), "content": content})
            except Exception:
                serialized.append({"role": "unknown", "content": str(m)[:512]})

        payload: dict[str, Any] = {"messages": serialized, "count": len(serialized)}

        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        # agent_name 为空时说明是 orchestrator (leader)
        is_leader = not agent_name or agent_name in ("orchestrator", "home-broadband-team")
        self.trace(
            "llm_prompt",
            payload,
            agent=agent_name or "orchestrator",
            is_leader=is_leader,
        )

    # ─── 流事件全量记录 (每个 agno 事件都调用) ─────────────────────────

    def stream_event(
        self,
        raw_event_type: str,
        *,
        agent: str = "",
        is_leader: bool = False,
        content: Any = None,
        tool_name: str = "",
        tool_args: Any = None,
        tool_result: Any = None,
    ) -> None:
        """记录 agno 流事件 — 用于完整重建 agent 交互过程。

        每个事件类型 (ReasoningContentDelta / ToolCallStarted / RunContent 等)
        都调用一次，不论前端是否渲染。
        """
        payload: dict[str, Any] = {"raw_event": raw_event_type}
        if content is not None:
            payload["content"] = str(content)[:2000]
        if tool_name:
            payload["tool_name"] = tool_name
        if tool_args is not None:
            payload["tool_args"] = tool_args
        if tool_result is not None:
            payload["tool_result"] = tool_result
        self.trace("stream_event", payload, agent=agent, is_leader=is_leader)

    # ─── 思考 ────────────────────────────────────────────────────────

    def thinking(self, content: str, *, agent: str = "", is_leader: bool = False) -> None:
        self.trace("thinking", {"content": content}, agent=agent, is_leader=is_leader)

    # ─── 工具调用 ────────────────────────────────────────────────────

    def tool_invoke(
        self, skill_name: str, inputs: Any, *, agent: str = "", is_leader: bool = False
    ) -> None:
        self.trace(
            "tool_invoke", {"skill": skill_name, "inputs": inputs}, agent=agent, is_leader=is_leader
        )

    def tool_result(
        self,
        skill_name: str,
        outputs: Any,
        latency_ms: int = 0,
        *,
        agent: str = "",
        is_leader: bool = False,
    ) -> None:
        self.trace(
            "tool_result",
            {"skill": skill_name, "outputs": outputs, "latency_ms": latency_ms},
            agent=agent,
            is_leader=is_leader,
        )

    # ─── SubAgent 交互 ──────────────────────────────────────────────

    def member_content(self, member_name: str, content: str) -> None:
        """记录 SubAgent 的文本回复内容。"""
        self.trace("member_content", {"content": content}, agent=member_name, is_leader=False)

    def member_completed(self, member_name: str, content: str = "") -> None:
        """记录 SubAgent 运行完成。"""
        self.trace("member_completed", {"content": content}, agent=member_name, is_leader=False)

    # ─── 错误 / 未处理事件 ──────────────────────────────────────────

    def unhandled_event(
        self, event_type: str, source_id: str = "", is_leader: bool = False
    ) -> None:
        """记录未处理的事件类型（用于调试缺失事件）。"""
        self.trace(
            "unhandled_event",
            {"event_type": event_type},
            agent=source_id,
            is_leader=is_leader,
        )

    def error(self, error_msg: str) -> None:
        self.trace("error", {"error": error_msg})
