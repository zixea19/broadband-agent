"""Gradio Web UI 入口 — 单用户多会话。"""

import sys
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import gradio as gr
from loguru import logger

# 确保项目根目录在 sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.observability.logger import setup_logger
from core.session_manager import SessionContext, session_manager
from core.observability.db import db
from ui.chat_renderer import render_thinking, render_tool_call, render_response

# 初始化日志
setup_logger()


async def chat_handler(
    message: str,
    history: List[Dict[str, Any]],
    session_state: Optional[Dict] = None,
) -> AsyncIterator[List[Dict[str, Any]]]:
    """Gradio chat handler — 异步流式输出。"""
    if not message or not message.strip():
        yield history
        return

    # 获取或创建会话
    session_hash = (session_state or {}).get("session_hash", str(uuid.uuid4()))
    ctx = session_manager.get_or_create(session_hash)

    # Trace: 记录用户请求
    ctx.tracer.request(message)
    db.insert_message(ctx.db_session_id, "user", message) if ctx.db_session_id else None

    # 添加用户消息到历史
    history = history + [{"role": "user", "content": message}]
    yield history

    # 运行 Agent (流式)
    try:
        from agno.run.agent import (
            RunEvent,
            RunContentEvent,
            RunCompletedEvent,
            ToolCallStartedEvent,
            ToolCallCompletedEvent,
            ReasoningStepEvent,
            ReasoningContentDeltaEvent,
        )

        full_content = ""
        reasoning_buffer = ""
        current_tool = None

        response_stream = ctx.agent.arun(
            message,
            session_id=session_hash,
            stream=True,
            stream_events=True,
        )

        async for event in response_stream:
            event_type = getattr(event, "event", "")

            # 思考/推理内容 (agno 内置推理引擎)
            if event_type == RunEvent.reasoning_content_delta.value:
                reasoning_buffer += getattr(event, "reasoning_content", "")
                thinking_msg = render_thinking(reasoning_buffer)
                yield history + [thinking_msg]

            elif event_type == RunEvent.reasoning_completed.value:
                if reasoning_buffer:
                    ctx.tracer.thinking(reasoning_buffer)
                    thinking_msg = render_thinking(reasoning_buffer)
                    history = history + [thinking_msg]
                    reasoning_buffer = ""

            # 工具调用开始
            elif event_type == RunEvent.tool_call_started.value:
                # 如果有待提交的思考内容，先提交到历史
                if reasoning_buffer:
                    ctx.tracer.thinking(reasoning_buffer)
                    history = history + [render_thinking(reasoning_buffer)]
                    reasoning_buffer = ""
                tool = getattr(event, "tool", None)
                if tool:
                    tool_name = getattr(tool, "tool_name", "") or getattr(tool, "function_name", "unknown")
                    tool_args = getattr(tool, "tool_args", None) or getattr(tool, "function_args", None)
                    ctx.tracer.tool_invoke(tool_name, tool_args)
                    tool_msg = render_tool_call(tool_name, inputs=tool_args)
                    yield history + [tool_msg]
                    current_tool = tool_name

            # 工具调用完成
            elif event_type == RunEvent.tool_call_completed.value:
                tool = getattr(event, "tool", None)
                if tool:
                    tool_name = getattr(tool, "tool_name", "") or getattr(tool, "function_name", current_tool or "unknown")
                    tool_result = getattr(tool, "result", None) or getattr(event, "content", None)
                    ctx.tracer.tool_result(tool_name, tool_result)
                    tool_msg = render_tool_call(tool_name, outputs=tool_result)
                    history = history + [tool_msg]
                    current_tool = None

            # 内容流（同时携带 reasoning_content 和 content）
            elif event_type == RunEvent.run_content.value:
                # 处理原生思考内容（Qwen/DeepSeek 等本地思考模型）
                reasoning_delta = getattr(event, "reasoning_content", None)
                if reasoning_delta:
                    reasoning_buffer += reasoning_delta
                    thinking_msg = render_thinking(reasoning_buffer)
                    yield history + [thinking_msg]

                # 当正式内容开始时，将思考内容固化到历史
                content_delta = getattr(event, "content", None)
                if content_delta is not None and reasoning_buffer:
                    ctx.tracer.thinking(reasoning_buffer)
                    history = history + [render_thinking(reasoning_buffer)]
                    reasoning_buffer = ""

                if content_delta:
                    full_content += str(content_delta)
                    yield history + [render_response(full_content)]

            # 运行完成
            elif event_type == RunEvent.run_completed.value:
                final = getattr(event, "content", None)
                if final and str(final) != full_content:
                    full_content = str(final)

        # 确保最终回答被添加
        if full_content:
            history = history + [render_response(full_content)]
            ctx.tracer.response(full_content)
            db.insert_message(ctx.db_session_id, "assistant", full_content) if ctx.db_session_id else None

        yield history

    except Exception as e:
        logger.exception("Agent 运行异常")
        ctx.tracer.error(str(e))
        error_msg = f"⚠️ 抱歉，处理请求时出现错误：{str(e)}"
        history = history + [render_response(error_msg)]
        yield history


_EXAMPLE_MESSAGES = [
    "直播套餐卖场走播用户，18:00-22:00 保障抖音直播",
    "生成 CEI 配置",
    "生成 Wifi 仿真配置",
    "生成故障检测配置",
    "生成远程闭环配置",
    "找出 CEI 分数较低的 PON 口并分析原因",
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
    """包装 chat_handler，在流式结束时同步恢复输入框和按钮。

    直接在最后一次 yield 中返回 gr.update(interactive=True)，
    避免使用 .then() 链式调用导致 gr.update dict 渗入 chatbot。
    """
    last_history = history
    async for h in chat_handler(message, history, session_state):
        last_history = h
        yield h, gr.update(), gr.update()   # 流式过程中不改变输入框/按钮状态
    # 流结束后，在最后一次 yield 里恢复交互
    yield last_history, gr.update(interactive=True), gr.update(interactive=True)


def create_app() -> gr.Blocks:
    """创建 Gradio 应用。"""
    with gr.Blocks(title="家宽网络调优助手", css=_CSS) as app:
        gr.Markdown("# 🏠 家宽网络调优智能助手")
        gr.Markdown("支持：综合目标设定 | 具体功能配置 | 数据洞察分析")

        session_state = gr.State(value={"session_hash": str(uuid.uuid4())})
        pending_msg = gr.State("")

        chatbot = gr.Chatbot(
            height=550,
            buttons=["copy", "copy_all"],
        )

        # 示例消息快捷按钮，分两行排列避免溢出
        gr.Markdown("**示例消息（点击发送）：**")
        example_btns = []
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

        # 示例按钮：捕获按钮文本 → 流式（含末尾恢复）
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

        # 发送按钮
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

        # 回车提交
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
