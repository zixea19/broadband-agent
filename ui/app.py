"""Gradio Web UI 入口 — 单用户多会话，驱动 agno Team。"""

import sys
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import gradio as gr
from loguru import logger

# 确保项目根目录在 sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.observability.logger import setup_logger
from core.observability.db import db
from core.session_manager import SessionContext, session_manager
from ui.chat_renderer import (
    render_member_badge,
    render_response,
    render_thinking,
    render_tool_call,
)

# 初始化日志
setup_logger()


# 把事件名中的 Team 前缀去掉便于统一匹配（Team 事件与 Agent 事件结构一致）
def _normalize_event_type(raw: str) -> str:
    if not raw:
        return ""
    if raw.startswith("Team"):
        return raw[len("Team"):]
    return raw


def _extract_member_name(event: Any) -> Optional[str]:
    """从事件对象上尝试识别当前发言的 SubAgent 名字。"""
    for attr in ("agent_name", "member_name", "from_agent", "agent_id"):
        val = getattr(event, attr, None)
        if val:
            return str(val)
    agent = getattr(event, "agent", None)
    if agent is not None:
        name = getattr(agent, "name", None)
        if name:
            return str(name)
    return None


async def chat_handler(
    message: str,
    history: List[Dict[str, Any]],
    session_state: Optional[Dict] = None,
) -> AsyncIterator[List[Dict[str, Any]]]:
    """Gradio chat handler — 异步流式输出 Team 事件。"""
    if not message or not message.strip():
        yield history
        return

    # 获取或创建会话
    session_hash = (session_state or {}).get("session_hash", str(uuid.uuid4()))
    ctx = session_manager.get_or_create(session_hash)

    # Trace 用户请求
    ctx.tracer.request(message)
    if ctx.db_session_id:
        db.insert_message(ctx.db_session_id, "user", message)

    # 添加用户消息到历史
    history = history + [{"role": "user", "content": message}]
    yield history

    full_content = ""
    reasoning_buffer = ""
    current_member: Optional[str] = None
    # 本轮已渲染过徽章的 member 集合 — 每个 SubAgent 只展示一次入场标记，
    # 避免并行执行时事件交错导致徽章反复切换重复渲染。
    seen_members: set = set()

    try:
        response_stream = ctx.team.arun(
            message,
            session_id=session_hash,
            stream=True,
            stream_events=True,
        )

        async for event in response_stream:
            raw_event_type = getattr(event, "event", "")
            event_type = _normalize_event_type(raw_event_type)

            # ---- 识别当前发言 SubAgent ----
            # 每次都更新 current_member 以反映最新事件来源 (供 tool_call 标签使用),
            # 但徽章只在该 member 首次出现时渲染一次。
            member = _extract_member_name(event)
            if member and member != ctx.team.name:
                current_member = member
                if member not in seen_members:
                    seen_members.add(member)
                    if reasoning_buffer:
                        ctx.tracer.thinking(reasoning_buffer)
                        history = history + [render_thinking(reasoning_buffer)]
                        reasoning_buffer = ""
                    history = history + [render_member_badge(member)]
                    yield history

            # ---- 思考/推理 ----
            if event_type == "ReasoningContentDelta":
                reasoning_buffer += getattr(event, "reasoning_content", "") or ""
                yield history + [render_thinking(reasoning_buffer)]

            elif event_type == "ReasoningCompleted":
                if reasoning_buffer:
                    ctx.tracer.thinking(reasoning_buffer)
                    history = history + [render_thinking(reasoning_buffer)]
                    reasoning_buffer = ""

            # ---- 工具调用开始 ----
            elif event_type == "ToolCallStarted":
                if reasoning_buffer:
                    ctx.tracer.thinking(reasoning_buffer)
                    history = history + [render_thinking(reasoning_buffer)]
                    reasoning_buffer = ""
                tool = getattr(event, "tool", None)
                if tool:
                    tool_name = (
                        getattr(tool, "tool_name", "")
                        or getattr(tool, "function_name", "unknown")
                    )
                    tool_args = (
                        getattr(tool, "tool_args", None)
                        or getattr(tool, "function_args", None)
                    )
                    ctx.tracer.tool_invoke(tool_name, tool_args)
                    yield history + [
                        render_tool_call(tool_name, inputs=tool_args, member=current_member)
                    ]

            # ---- 工具调用完成 ----
            elif event_type == "ToolCallCompleted":
                tool = getattr(event, "tool", None)
                if tool:
                    tool_name = (
                        getattr(tool, "tool_name", "")
                        or getattr(tool, "function_name", "unknown")
                    )
                    tool_result = getattr(tool, "result", None) or getattr(
                        event, "content", None
                    )
                    ctx.tracer.tool_result(tool_name, tool_result)
                    history = history + [
                        render_tool_call(tool_name, outputs=tool_result, member=current_member)
                    ]

            # ---- 内容流 ----
            elif event_type == "RunContent":
                # 本地原生思考内容 (Qwen/DeepSeek)
                reasoning_delta = getattr(event, "reasoning_content", None)
                if reasoning_delta:
                    reasoning_buffer += reasoning_delta
                    yield history + [render_thinking(reasoning_buffer)]

                content_delta = getattr(event, "content", None)
                if content_delta is not None and reasoning_buffer:
                    ctx.tracer.thinking(reasoning_buffer)
                    history = history + [render_thinking(reasoning_buffer)]
                    reasoning_buffer = ""

                # 只有 Team leader (orchestrator) 的 content 才累积到最终回答
                # member 的 content 已经在 tool_call 里体现
                if content_delta and (
                    current_member is None or current_member == ctx.team.name
                ):
                    full_content += str(content_delta)
                    yield history + [render_response(full_content)]

            # ---- 运行完成 ----
            elif event_type == "RunCompleted":
                final = getattr(event, "content", None)
                if final and str(final) != full_content:
                    full_content = str(final)

        # 确保最终回答被添加
        if full_content:
            history = history + [render_response(full_content)]
            ctx.tracer.response(full_content)
            if ctx.db_session_id:
                db.insert_message(ctx.db_session_id, "assistant", full_content)

        yield history

    except Exception as e:
        logger.exception("Team 运行异常")
        ctx.tracer.error(str(e))
        error_msg = f"⚠️ 抱歉，处理请求时出现错误：{str(e)}"
        history = history + [render_response(error_msg)]
        yield history


_EXAMPLE_MESSAGES = [
    "直播套餐卖场走播用户，18:00-22:00 保障抖音直播",
    "找出 CEI 分数较低的 PON 口并分析原因",
    "查看当前 WIFI 覆盖",
    "开通抖音应用切片",
    "立即进行网关重启",
    "用户卡顿，请定界",
]

_CSS = """
/* 统一正文字体，避免 CEI 等大写字母被渲染成衬线/花体 */
.gradio-container, .gradio-container * {
    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC",
                 "Helvetica Neue", Arial, sans-serif !important;
}
/* 示例消息按钮样式 */
.example-btn {
    font-size: 0.85em !important;
    padding: 4px 10px !important;
    border-radius: 14px !important;
    border: 1px solid #d0d7de !important;
    background: #f6f8fa !important;
    color: #24292f !important;
    cursor: pointer;
}
.example-btn:hover {
    background: #e9ecef !important;
    border-color: #b0b7c0 !important;
}
"""


async def _streaming_with_reenable(message, history, session_state):
    """包装 chat_handler，在流式结束时同步恢复输入框和按钮。"""
    last_history = history
    async for h in chat_handler(message, history, session_state):
        last_history = h
        yield h, gr.update(), gr.update()  # 流式过程中不改变输入框/按钮状态
    # 流结束后恢复交互
    yield last_history, gr.update(interactive=True), gr.update(interactive=True)


def create_app() -> gr.Blocks:
    """创建 Gradio 应用。"""
    with gr.Blocks(title="家宽网络调优助手", css=_CSS) as app:
        gr.Markdown("# 🏠 家宽网络调优智能助手")
        gr.Markdown(
            "Team 架构：Orchestrator 路由 → PlanningAgent / InsightAgent / "
            "ProvisioningAgent × 3"
        )

        session_state = gr.State(value={"session_hash": str(uuid.uuid4())})
        pending_msg = gr.State("")

        chatbot = gr.Chatbot(
            height=550,
            buttons=["copy", "copy_all"],
        )

        gr.Markdown("**示例消息（点击发送）：**")
        example_btns: List[gr.Button] = []
        rows = [_EXAMPLE_MESSAGES[:3], _EXAMPLE_MESSAGES[3:]]
        for row_msgs in rows:
            with gr.Row():
                for msg in row_msgs:
                    example_btns.append(
                        gr.Button(msg, elem_classes=["example-btn"], size="sm")
                    )

        with gr.Row():
            msg_input = gr.Textbox(
                placeholder="输入消息，或点击上方示例...",
                show_label=False,
                scale=9,
                container=False,
            )
            send_btn = gr.Button("发送", variant="primary", scale=1)

        with gr.Row():
            clear_btn = gr.Button("🗑️ 清空对话")
            new_session_btn = gr.Button("🔄 新建会话")

        def _capture_msg(msg):
            """暂存消息、立即清空输入框、禁用发送按钮。"""
            return (
                msg,
                gr.update(value="", interactive=False),
                gr.update(interactive=False),
            )

        for btn in example_btns:
            btn.click(
                fn=_capture_msg,
                inputs=[btn],
                outputs=[pending_msg, msg_input, send_btn],
                queue=False,
            ).then(
                fn=_streaming_with_reenable,
                inputs=[pending_msg, chatbot, session_state],
                outputs=[chatbot, msg_input, send_btn],
            )

        send_btn.click(
            fn=_capture_msg,
            inputs=[msg_input],
            outputs=[pending_msg, msg_input, send_btn],
            queue=False,
        ).then(
            fn=_streaming_with_reenable,
            inputs=[pending_msg, chatbot, session_state],
            outputs=[chatbot, msg_input, send_btn],
        )

        msg_input.submit(
            fn=_capture_msg,
            inputs=[msg_input],
            outputs=[pending_msg, msg_input, send_btn],
            queue=False,
        ).then(
            fn=_streaming_with_reenable,
            inputs=[pending_msg, chatbot, session_state],
            outputs=[chatbot, msg_input, send_btn],
        )

        clear_btn.click(lambda: [], outputs=[chatbot])

        def new_session():
            new_hash = str(uuid.uuid4())
            return [], {"session_hash": new_hash}

        new_session_btn.click(fn=new_session, outputs=[chatbot, session_state])

    return app


if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=True,
        theme=gr.themes.Soft(),
    )
