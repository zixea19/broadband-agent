#!/usr/bin/env python3
"""NL2Code 沙筐执行脚本 — data_insight Skill 的执行单元之三。

先按三元组查询数据，再在受限沙筐中执行 LLM 生成的 pandas 代码。
**注意**：代码由 InsightAgent 自己生成后传入，**不在本脚本内调用 LLM**。

输入（argv[1]）：JSON 字符串，形如
    {
        "code": "result = df.nsmallest(3, 'CEI_score')",
        "query_config": {三元组},
        "table_level": "day" | "minute",
        "data_path": "mock",
        "code_prompt": "取 CEI_score 最低的 3 个 portUuid",
        "phase_id": 1,
        "step_id": 1
    }

输出（stdout）：JSON 字符串，形如
    {
        "status": "ok" | "error",
        "skill": "insight_nl2code",
        "op": "run_nl2code",
        "result": {type: ..., ...},
        "description": "NL2Code 分析完成: ...",
        "fix_warnings": [...],
        "data_shape": [row, col],
        "phase_id": int | null,
        "step_id": int | null
    }

沙筐安全措施：AST 校验 + builtins 白名单（禁止 import / open / exec / 魔术属性）。
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

try:
    import ce_insight_core as cic
    from ce_insight_core.sandbox import summarize_nl2code_result
except ImportError as exc:
    print(
        json.dumps(
            {
                "status": "error",
                "skill": "insight_nl2code",
                "op": "run_nl2code",
                "error": f"ce_insight_core 未安装: {exc}",
            },
            ensure_ascii=False,
        )
    )
    sys.exit(1)


def _safe_parse_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    stripped = raw.strip()
    if stripped.startswith("'") and stripped.endswith("'"):
        stripped = stripped[1:-1]
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    _candidate = raw.strip()
    if _candidate.startswith("{") and _candidate.endswith("]"):
        try:
            return json.loads(_candidate[:-1] + "}")
        except json.JSONDecodeError:
            pass
    repaired = re.sub(r"(?<=[{,])\s*([a-zA-Z_]\w*)\s*:", r' "\1":', raw)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass
    try:
        from json_repair import repair_json
        return json.loads(repair_json(raw, return_objects=False))
    except (ImportError, Exception):
        pass
    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                return json.loads(stdin_data)
        except Exception:
            pass
    return json.loads(raw)


def _resolve_data_path(table_level: str) -> str:
    try:
        import yaml
        config_path = Path(__file__).resolve().parents[3] / "configs" / "data_paths.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            key = "minute_table_path" if table_level == "minute" else "day_table_path"
            return cfg.get(key, "mock") or "mock"
    except Exception:
        pass
    return "mock"


def run(payload_json: str) -> str:
    try:
        payload: dict[str, Any] = _safe_parse_json(payload_json)
    except json.JSONDecodeError as exc:
        return _err(f"payload JSON 解析失败: {exc}")

    code = payload.get("code", "")
    if not code or not isinstance(code, str):
        return _err("payload 缺少 code 或类型非 str")

    query_config = payload.get("query_config")
    if not isinstance(query_config, dict):
        return _err("payload 缺少 query_config 或类型非 dict")

    table_level = payload.get("table_level", "day")
    if table_level not in ("day", "minute"):
        return _err(f"table_level 必须是 day/minute，收到: {table_level}")

    data_path = payload.get("data_path") or _resolve_data_path(table_level)
    code_prompt = payload.get("code_prompt", "")

    try:
        fixed_config, fix_warnings = cic.fix_query_config(query_config, table_level=table_level)
    except Exception as exc:
        return _err(f"fix_query_config 失败: {type(exc).__name__}: {exc}")

    try:
        dfs = cic.query_subject_pandas(fixed_config, data_path)
    except Exception as exc:
        return _err(f"查询失败: {type(exc).__name__}: {exc}")

    if not dfs or dfs[0].empty:
        return _err("查询返回空 DataFrame")

    df = dfs[0]

    try:
        raw_result = cic.run_nl2code(code, df)
    except cic.NL2CodeError as exc:
        return _err(f"NL2CodeError: {exc}")
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}")

    serialized = summarize_nl2code_result(raw_result)
    description = _build_description(serialized, code_prompt)

    output: dict[str, Any] = {
        "status": "ok",
        "skill": "insight_nl2code",
        "op": "run_nl2code",
        "result": serialized,
        "description": description,
        "fix_warnings": fix_warnings,
        "data_shape": list(df.shape),
        "phase_id": payload.get("phase_id"),
        "step_id": payload.get("step_id"),
    }
    return json.dumps(output, ensure_ascii=False, default=_json_default)


def _build_description(serialized: dict[str, Any], code_prompt: str) -> str:
    prefix = f"NL2Code 分析完成 — {code_prompt}" if code_prompt else "NL2Code 分析完成"
    t = serialized.get("type")
    if t == "dataframe":
        shape = serialized.get("shape", [0, 0])
        return f"{prefix}；结果 {shape[0]} 行 x {shape[1]} 列"
    if t == "dict":
        return f"{prefix}；结果: {str(serialized.get('value', ''))[:200]}"
    if t == "list":
        return f"{prefix}；结果列表长度 {len(serialized.get('value', []))}"
    if t == "none":
        return f"{prefix}；result 未赋值"
    return f"{prefix}；结果: {serialized.get('text', '')[:200]}"


def _err(msg: str) -> str:
    return json.dumps(
        {
            "status": "error",
            "skill": "insight_nl2code",
            "op": "run_nl2code",
            "error": msg,
        },
        ensure_ascii=False,
    )


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
