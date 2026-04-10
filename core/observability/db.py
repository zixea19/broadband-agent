"""SQLite schema 初始化与 DAO 层。

所有写操作均 try/except 包裹，失败不影响主流程。
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "sessions.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_hash TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    ended_at TEXT,
    user_agent TEXT,
    task_type TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    created_at TEXT NOT NULL,
    parent_msg_id INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    message_id INTEGER,
    skill_name TEXT,
    inputs_json TEXT,
    outputs_json TEXT,
    latency_ms INTEGER,
    status TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    session_hash TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """SQLite DAO — 线程安全（每次操作独立连接 or 使用 check_same_thread=False）。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        try:
            conn = self._get_conn()
            conn.executescript(_SCHEMA_SQL)
            # 兼容旧 schema：traces 表可能缺少 session_hash 列
            try:
                conn.execute("ALTER TABLE traces ADD COLUMN session_hash TEXT NOT NULL DEFAULT ''")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # 列已存在，忽略
            # 自检：验证表存在且可写
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            conn.close()
            logger.info(f"SQLite schema 初始化完成: {self.db_path}, tables={tables}")
        except Exception:
            logger.exception(f"SQLite schema 初始化失败: {self.db_path}")

    # ---- sessions ----
    def create_session(self, session_hash: str, user_agent: str = "") -> Optional[int]:
        try:
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT INTO sessions (session_hash, created_at, user_agent) VALUES (?, ?, ?)",
                (session_hash, _now_iso(), user_agent),
            )
            conn.commit()
            sid = cur.lastrowid
            conn.close()
            logger.debug(f"create_session 成功: session_hash={session_hash[:8]}..., db_sid={sid}")
            return sid
        except Exception:
            logger.exception(f"create_session 失败: session_hash={session_hash[:8]}..., db_path={self.db_path}")
            return None

    def end_session(self, session_hash: str, task_type: str = "") -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                "UPDATE sessions SET ended_at=?, task_type=? WHERE session_hash=?",
                (_now_iso(), task_type, session_hash),
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("end_session 失败")

    def get_session_id(self, session_hash: str) -> Optional[int]:
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT id FROM sessions WHERE session_hash=?", (session_hash,)
            ).fetchone()
            conn.close()
            return row["id"] if row else None
        except Exception:
            logger.exception("get_session_id 失败")
            return None

    # ---- messages ----
    def insert_message(self, session_id: int, role: str, content: str, parent_msg_id: Optional[int] = None) -> Optional[int]:
        try:
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at, parent_msg_id) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, _now_iso(), parent_msg_id),
            )
            conn.commit()
            mid = cur.lastrowid
            conn.close()
            logger.debug(f"insert_message 成功: session_id={session_id}, role={role}, mid={mid}")
            return mid
        except Exception:
            logger.exception(f"insert_message 失败: session_id={session_id}, role={role}")
            return None

    # ---- tool_calls ----
    def insert_tool_call(
        self,
        session_id: int,
        skill_name: str,
        inputs_json: str,
        outputs_json: str = "",
        latency_ms: int = 0,
        status: str = "ok",
        message_id: Optional[int] = None,
    ) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO tool_calls (session_id, message_id, skill_name, inputs_json, outputs_json, latency_ms, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, message_id, skill_name, inputs_json, outputs_json, latency_ms, status, _now_iso()),
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("insert_tool_call 失败")

    # ---- traces ----
    def insert_trace(self, session_id: int, session_hash: str, event_type: str, payload: Any = None) -> None:
        try:
            payload_str = json.dumps(payload, ensure_ascii=False, default=str) if payload else "{}"
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO traces (session_id, session_hash, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, session_hash, event_type, payload_str, _now_iso()),
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("insert_trace 失败")


# 全局单例
db = Database()
