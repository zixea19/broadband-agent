"""折叠思考/工具调用的消息渲染逻辑。

将 agno Team 的流式事件映射为 Gradio ChatMessage 格式。
"""

import json
from typing import Any, Dict, Optional


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
) -> Dict[str, Any]:
    """渲染工具调用为折叠块。

    对 Skill 脚本执行结果（outputs 含 stdout 键）按内容类型分别渲染：
    - stdout 以 '#' 开头（Markdown 报告）：直接嵌入
    - stdout 为 JSON 内容：包裹在代码块中
    """
    parts = []
    if inputs is not None:
        parts.append(f"**输入参数**:\n```json\n{_format_json(inputs)}\n```")
    if outputs is not None:
        if isinstance(outputs, dict) and "stdout" in outputs:
            script_path = outputs.get("script_path", "")
            returncode = outputs.get("returncode", 0)
            stdout = (outputs.get("stdout") or "").strip()
            stderr = (outputs.get("stderr") or "").strip()
            status = "✅" if returncode == 0 else "❌"
            parts.append(f"{status} `{script_path}` (returncode={returncode})")
            if stdout:
                if stdout.startswith("#"):
                    parts.append(stdout)
                else:
                    parts.append(f"```json\n{stdout}\n```")
            if stderr:
                parts.append(f"**stderr**:\n```\n{stderr}\n```")
        else:
            parts.append(f"**返回结果**:\n```json\n{_format_json(outputs)}\n```")
    content = "\n\n".join(parts) if parts else "调用中..."

    title_prefix = f"🔧 调用 {skill_name}"
    if member:
        title_prefix = f"🔧 [{_display_agent(member)}] 调用 {skill_name}"

    return {
        "role": "assistant",
        "metadata": {"title": title_prefix},
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
