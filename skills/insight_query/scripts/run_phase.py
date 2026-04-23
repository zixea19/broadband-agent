#!/usr/bin/env python3
"""Phase 批量执行脚本 — 将同一 Phase 内所有标准 Step 合并为单次工具调用。

输入（argv[1]）：JSON 字符串，形如
    {
        "phase_id": 1,
        "phase_name": "定位低分PON口",
        "table_level": "day",
        "steps": [
            {
                "step_id": 1,
                "step_name": "找出 CEI_score 最低的 PON 口",
                "insight_type": "OutstandingMin",
                "query_config": {
                    "dimensions": [[]],
                    "breakdown": {"name": "portUuid", "type": "UNORDERED"},
                    "measures": [{"name": "CEI_score", "aggr": "AVG"}]
                }
            }
        ]
    }

输出（stdout）：JSON 字符串，形如
    {
        "status": "ok",
        "skill": "insight_query",
        "op": "run_phase",
        "phase_id": 1,
        "phase_name": "定位低分PON口",
        "table_level": "day",
        "overall_status": "ok",
        "results": [
            {
                "step_id": 1,
                "step_name": "找出 CEI_score 最低的 PON 口",
                "insight_type": "OutstandingMin",
                "status": "ok",
                "significance": 0.73,
                "description": {"summary": "...", "min_group": "uuid-a"},
                "filter_data": [{"portUuid": "uuid-a", "CEI_score": 54.08}],
                "has_chart": true,
                "chart_file": "/tmp/xxx.json",
                "found_entities": {"portUuid": ["uuid-a", "uuid-b"]},
                "data_shape": [3857, 2]
            }
        ]
    }

overall_status：任意一个 step 成功则为 "ok"；全部失败才为 "error"。

实现要点：
  - 直接 from run_insight import run as run_single，函数调用不走子进程
  - 对 steps[] 逐项构造 payload（注入 phase_id/phase_name/step_id/step_name/table_level）
  - 每个结果反序列化后收集进 results[]，chart_file 路径原样保留（event_adapter 读取后删除）
  - 单步异常捕获：写入该 step 的 status="error"，继续执行其余 step
"""

import json
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# 直接导入 run_insight.run，函数调用不走子进程，节省 N-1 次 LLM round-trip
try:
    from run_insight import run as run_single
except ImportError as exc:
    print(
        json.dumps(
            {
                "status": "error",
                "skill": "insight_query",
                "op": "run_phase",
                "error": f"无法导入 run_insight: {exc}",
            },
            ensure_ascii=False,
        )
    )
    sys.exit(1)


def _err_phase(msg: str, phase_id: Any = None, phase_name: str = "") -> str:
    return json.dumps(
        {
            "status": "error",
            "skill": "insight_query",
            "op": "run_phase",
            "phase_id": phase_id,
            "phase_name": phase_name,
            "error": msg,
        },
        ensure_ascii=False,
    )


def run(payload_json: str) -> str:
    """主入口：解析 Phase payload → 逐步调 run_single → 聚合 results[]。"""
    try:
        payload: dict[str, Any] = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        return _err_phase(f"payload JSON 解析失败: {exc}")

    phase_id = payload.get("phase_id")
    phase_name = str(payload.get("phase_name") or "")
    table_level = str(payload.get("table_level") or "day")
    steps = payload.get("steps")

    if not isinstance(steps, list) or not steps:
        return _err_phase("payload 缺少 steps 列表或列表为空", phase_id, phase_name)

    results: list[dict] = []
    any_ok = False

    for step in steps:
        if not isinstance(step, dict):
            results.append({
                "status": "error",
                "error": "step 格式非 dict",
            })
            continue

        step_id = step.get("step_id")
        step_name = str(step.get("step_name") or "")
        insight_type = step.get("insight_type", "")
        query_config = step.get("query_config")

        # 构造单步 payload，注入 Phase 级字段
        single_payload: dict[str, Any] = {
            "insight_type": insight_type,
            "query_config": query_config,
            "table_level": table_level,
            "phase_id": phase_id,
            "phase_name": phase_name,
            "step_id": step_id,
            "step_name": step_name,
        }

        try:
            result_str = run_single(json.dumps(single_payload, ensure_ascii=False))
            result_dict: dict = json.loads(result_str)
        except Exception as exc:
            result_dict = {
                "status": "error",
                "skill": "insight_query",
                "op": "run_insight",
                "insight_type": insight_type,
                "error": f"{type(exc).__name__}: {exc}",
                "phase_id": phase_id,
                "phase_name": phase_name,
                "step_id": step_id,
                "step_name": step_name,
            }

        if result_dict.get("status") == "ok":
            any_ok = True

        # 只保留前端 / event_adapter 所需字段，丢弃 skill/op 等元信息字段
        step_result: dict[str, Any] = {
            "step_id": step_id,
            "step_name": step_name,
            "insight_type": result_dict.get("insight_type", insight_type),
            "status": result_dict.get("status", "error"),
            "significance": result_dict.get("significance", 0.0),
            "description": result_dict.get("description", ""),
            "filter_data": result_dict.get("filter_data", []),
            "has_chart": result_dict.get("has_chart", False),
            "chart_file": result_dict.get("chart_file"),
            "fix_warnings": result_dict.get("fix_warnings", []),
            "found_entities": result_dict.get("found_entities", {}),
            "data_shape": result_dict.get("data_shape", []),
            "phase_id": phase_id,
            "phase_name": phase_name,
        }
        if "error" in result_dict:
            step_result["error"] = result_dict["error"]

        results.append(step_result)

    overall_status = "ok" if any_ok else "error"

    output: dict[str, Any] = {
        "status": overall_status,
        "skill": "insight_query",
        "op": "run_phase",
        "phase_id": phase_id,
        "phase_name": phase_name,
        "table_level": table_level,
        "overall_status": overall_status,
        "results": results,
    }
    return json.dumps(output, ensure_ascii=False, default=_json_default)


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            return str(obj)
    return str(obj)


if __name__ == "__main__":
    _payload = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(run(_payload))
