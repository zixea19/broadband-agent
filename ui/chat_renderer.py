"""折叠思考/工具调用的消息渲染逻辑。

将 agno 的流式事件映射为 Gradio ChatMessage 格式。
"""

from typing import Any, Dict, List, Optional


def render_thinking(content: str) -> Dict[str, Any]:
    """渲染思考过程为折叠块。"""
    return {
        "role": "assistant",
        "metadata": {"title": "💭 思考"},
        "content": content,
    }


def render_tool_call(skill_name: str, inputs: Any = None, outputs: Any = None) -> Dict[str, Any]:
    """渲染工具调用为折叠块。

    对 Skill 脚本执行结果（outputs 含 stdout 键）按内容类型分别渲染：
    - stdout 以 '#' 开头（Markdown 报告）：直接嵌入，Gradio 渲染为 Markdown
    - stdout 为 JSON 内容：包裹在代码块中
    - 其余 tool result（无 stdout 键）：保持现有 JSON 格式
    """
    parts = []
    if inputs is not None:
        parts.append(f"**输入参数**:\n```json\n{_format_json(inputs)}\n```")
    if outputs is not None:
        if isinstance(outputs, dict) and "stdout" in outputs:
            script_path = outputs.get("script_path", "")
            returncode = outputs.get("returncode", 0)
            stdout = outputs.get("stdout", "").strip()
            stderr = outputs.get("stderr", "").strip()
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

    return {
        "role": "assistant",
        "metadata": {"title": f"🔧 调用 {skill_name}"},
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
    import json
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return str(data)
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(data)
