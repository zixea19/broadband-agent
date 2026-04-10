"""折叠思考/工具调用的消息渲染逻辑。

将 agno Team 的流式事件映射为 Gradio ChatMessage 格式。
"""

import json
from typing import Any, Dict, List, Optional


# ─── Agent 中文显示名（用于徽章标题） ───
_AGENT_DISPLAY_NAMES = {
    "home-broadband-team": "Orchestrator",
    "planning": "PlanningAgent",
    "insight": "InsightAgent",
    "provisioning_wifi": "ProvisioningAgent (WIFI 仿真)",
    "provisioning_delivery": "ProvisioningAgent (差异化承载)",
    "provisioning_cei_chain": "ProvisioningAgent (体验保障链)",
}


def _display_agent(name: str) -> str:
    return _AGENT_DISPLAY_NAMES.get(name, name)


def render_member_badge(member_name: str) -> Dict[str, Any]:
    """渲染一个 SubAgent 徽章，提示"当前发言者是谁"。"""
    display = _display_agent(member_name)
    return {
        "role": "assistant",
        "metadata": {"title": f"👤 {display}"},
        "content": f"由 **{display}** 接手处理",
    }


def render_thinking(content: str, member: Optional[str] = None) -> Dict[str, Any]:
    """渲染思考过程为折叠块。

    Args:
        content: 思考内容文本
        member: 发言 SubAgent 名字 (如 "provisioning_wifi"), 非空时标题会带上
            中文显示名,便于并行执行时区分不同 member 的思考块。
    """
    title = "💭 思考"
    if member:
        title = f"💭 [{_display_agent(member)}] 思考"
    return {
        "role": "assistant",
        "metadata": {"title": title},
        "content": content,
    }


def render_tool_call(
    skill_name: str,
    inputs: Any = None,
    outputs: Any = None,
    member: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """渲染工具调用事件为一个或两个 Gradio ChatMessage。

    对 Skill 脚本执行结果（outputs 为 dict 且含 `stdout` 键），会**拆成两条**：

    1. **折叠块**（带 ``metadata.title``）：输入参数 / script_path / returncode /
       stderr — 审计信息，默认折叠。
    2. **展开块**（无 ``metadata.title``）：stdout 正文 — 默认可见，用户无需点击；
       Agent 因此可以省去"在 assistant 文本里复述 stdout"的开销，节省 token 并
       避免改写风险。

    其他情况（inputs-only 进行中、outputs 非 Skill 格式）返回单条折叠块。

    Returns:
        List[ChatMessage] — 调用方用 ``history + render_tool_call(...)`` 追加，
        **不要**再用 ``[render_tool_call(...)]`` 二次包裹。
    """
    meta_parts: List[str] = []
    if inputs is not None:
        meta_parts.append(f"**输入参数**:\n```json\n{_format_json(inputs)}\n```")

    stdout_body: Optional[str] = None       # 非空则追加展开块
    stdout_is_markdown = False

    if outputs is not None:
        # agno 在不同版本下可能把 Skill 脚本返回值序列化为 JSON 字符串后
        # 再放入 ToolCallCompleted.tool.result,这里统一先尝试解析成 dict,
        # 避免走到下面的 "返回结果" 兜底分支、丢失 skill 格式拆分能力。
        parsed = outputs
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except (json.JSONDecodeError, TypeError):
                pass  # 非 JSON 字符串,保持原样交给兜底分支展示

        if isinstance(parsed, dict) and "stdout" in parsed:
            script_path = parsed.get("script_path", "")
            returncode = parsed.get("returncode", 0)
            stdout = (parsed.get("stdout") or "").strip()
            stderr = (parsed.get("stderr") or "").strip()
            status = "✅" if returncode == 0 else "❌"
            meta_parts.append(f"{status} `{script_path}` (returncode={returncode})")
            if stderr:
                meta_parts.append(f"**stderr**:\n```\n{stderr}\n```")
            if stdout:
                stdout_body = stdout
                stdout_is_markdown = stdout.startswith("#")
        else:
            meta_parts.append(f"**返回结果**:\n```json\n{_format_json(outputs)}\n```")

    meta_content = "\n\n".join(meta_parts) if meta_parts else "调用中..."

    title_prefix = f"🔧 调用 {skill_name}"
    if member:
        title_prefix = f"🔧 [{_display_agent(member)}] 调用 {skill_name}"

    messages: List[Dict[str, Any]] = [
        {
            "role": "assistant",
            "metadata": {"title": title_prefix},
            "content": meta_content,
        }
    ]

    if stdout_body:
        if stdout_is_markdown:
            body_text = stdout_body
        else:
            body_text = f"```json\n{stdout_body}\n```"

        header = f"**{skill_name} 产出**"
        if member:
            header = f"**[{_display_agent(member)}] {skill_name} 产出**"

        messages.append(
            {
                "role": "assistant",
                "content": f"{header}\n\n{body_text}",
            }
        )

    return messages


def render_member_content(content: str, member: Optional[str] = None) -> Dict[str, Any]:
    """渲染 SubAgent 的文本回复内容（折叠块）。

    Args:
        content: SubAgent 生成的文本内容
        member: SubAgent 名字（如 "insight"），用于标题显示
    """
    title = "📝 SubAgent 回复"
    if member:
        title = f"📝 [{_display_agent(member)}] 回复"
    return {
        "role": "assistant",
        "metadata": {"title": title},
        "content": content,
    }


def render_response(content: str) -> Dict[str, Any]:
    """渲染最终回答。"""
    return {
        "role": "assistant",
        "content": content,
    }


def _format_json(data: Any) -> str:
    """将数据格式化为 JSON 字符串。"""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return str(data)
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(data)
