"""业务追踪层 — 订阅 agno 事件流，落到 SQLite + JSONL。

写入失败绝不影响主流程。
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from core.observability.db import db

_TRACE_DIR = Path(__file__).resolve().parents[2] / "data" / "logs" / "trace"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_jsonl(event_type: str, session_hash: str, payload: Any) -> None:
    """追加一行到当天的 JSONL 文件。"""
    try:
        _TRACE_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = _TRACE_DIR / f"{today}.jsonl"
        line = json.dumps(
            {
                "ts": _now_iso(),
                "session": session_hash,
                "event": event_type,
                "payload": payload,
            },
            ensure_ascii=False,
            default=str,
        )
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        print(f"[tracer] JSONL write failed: {event_type}", file=sys.stderr)


class Tracer:
    """会话级 Tracer — 绑定到一个 session_hash。"""

    def __init__(self, session_hash: str, db_session_id: Optional[int] = None):
        self.session_hash = session_hash
        self.db_session_id = db_session_id

    def trace(self, event_type: str, payload: Any = None) -> None:
        """写入一条 trace 事件（SQLite + JSONL 双写）。"""
        try:
            if self.db_session_id is not None:
                db.insert_trace(self.db_session_id, self.session_hash, event_type, payload)
            _write_jsonl(event_type, self.session_hash, payload)
        except Exception:
            print(f"[tracer] trace write failed: {event_type}", file=sys.stderr)

    def request(self, user_input: str) -> None:
        self.trace("request", {"input": user_input})

    def llm_prompt(self, messages: list) -> None:
        """记录发送给 LLM 的完整消息列表（system + history + user）。"""
        serialized = []
        for m in messages:
            try:
                role = getattr(m, "role", "unknown")
                content = getattr(m, "content", "")
                if isinstance(content, str):
                    # tool 返回值通常是 ensure_ascii=True 的 JSON 字符串，
                    # 先解析再用 ensure_ascii=False 重新序列化，还原可读中文
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
        self.trace("llm_prompt", {"messages": serialized, "count": len(serialized)})

    def thinking(self, content: str) -> None:
        self.trace("thinking", {"content": content})

    def tool_invoke(self, skill_name: str, inputs: Any) -> None:
        self.trace("tool_invoke", {"skill": skill_name, "inputs": inputs})

    def tool_result(self, skill_name: str, outputs: Any, latency_ms: int = 0) -> None:
        self.trace("tool_result", {"skill": skill_name, "outputs": outputs, "latency_ms": latency_ms})

    def response(self, content: str) -> None:
        self.trace("response", {"content": content})

    def error(self, error_msg: str) -> None:
        self.trace("error", {"error": error_msg})
