#!/usr/bin/env python3
"""方案模板渲染脚本 — 根据用户画像渲染四类配置。

作为 agno Skill 脚本被调用。
"""

import json
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "references"


def render_all(profile_json: str) -> str:
    """渲染所有四类配置模板。

    Args:
        profile_json: 用户画像 JSON 字符串

    Returns:
        包含四类配置的 JSON 结果
    """
    try:
        profile = json.loads(profile_json) if isinstance(profile_json, str) else profile_json
    except json.JSONDecodeError:
        return json.dumps({"error": "无效的画像 JSON"}, ensure_ascii=False)

    # 设置默认值
    defaults = {
        "user_type": "主播用户",
        "package_type": "普通套餐",
        "scenario": "家庭直播",
        "guarantee_target": "家庭网络",
        "time_window": "全天",
        "complaint_history": False,
    }
    ctx = {**defaults, **profile}

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )

    results = {}
    templates = {
        "cei_config": "cei_spark.yaml.j2",
        "fault_config": "fault_api.json.j2",
        "remote_loop": "remote_loop.json.j2",
        "wifi_simulation": "wifi_sim.yaml.j2",
    }

    for config_name, template_file in templates.items():
        try:
            tmpl = env.get_template(template_file)
            rendered = tmpl.render(**ctx)
            results[config_name] = rendered
        except Exception as e:
            results[config_name] = f"渲染失败: {str(e)}"

    return json.dumps(results, ensure_ascii=False, indent=2)


def render_from_insight(profile_json: str) -> str:
    """数据洞察模式下的方案渲染。

    接收 Agent 推断后的画像（含 config_hints），渲染标准四类配置，
    并附加结构化的 optimization_focus 块供 Agent 在最终回答中综合引用。
    不在此函数中生成文字推荐——文字叙述由 LLM 负责。

    [扩展点] 后续可将 config_hints 字段注入 Jinja2 模板（如在 CEI 模板中
    直接填充 priority_pons 作为 target_pon），实现精细化渲染。
    """
    try:
        profile = json.loads(profile_json) if isinstance(profile_json, str) else profile_json
    except json.JSONDecodeError:
        return json.dumps({"error": "无效的画像 JSON"}, ensure_ascii=False)

    # 渲染标准四类配置（复用现有逻辑）
    base_result = json.loads(render_all(profile_json))

    # 附加洞察专属结构（结构化数据，不生成推荐文字）
    hints = profile.get("config_hints", {})
    base_result["optimization_focus"] = {
        "trigger":                "data_insight",
        "priority_pons":          hints.get("priority_pons", []),
        "watch_pons":             hints.get("watch_pons", []),
        "distinct_issues":        hints.get("distinct_issues", []),
        "remote_loop_candidates": hints.get("remote_loop_candidates", []),
        "peak_time_window":       hints.get("peak_time_window"),
        "scope_indicator":        hints.get("scope_indicator"),
        "total_complaints_7d":    hints.get("total_complaints_7d", 0),
    }

    return json.dumps(base_result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _input = sys.argv[1]
        try:
            _profile = json.loads(_input)
        except json.JSONDecodeError:
            print(json.dumps({"error": "无效的画像 JSON"}, ensure_ascii=False))
            sys.exit(1)
        if _profile.get("mode") == "data_insight":
            print(render_from_insight(_input))
        else:
            print(render_all(_input))
    else:
        sample = json.dumps({
            "user_type": "主播用户",
            "package_type": "直播套餐",
            "scenario": "卖场走播",
            "guarantee_target": "STA级",
            "time_window": "18:00-22:00",
        })
        print(render_all(sample))
