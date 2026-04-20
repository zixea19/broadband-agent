---
name: insight_query
description: "三元组数据查询 + 12 种洞察函数执行，返回 significance / chart_configs / found_entities"
---

# 洞察查询与分析

## Metadata
- **paradigm**: Tool Wrapper
- **when_to_use**: InsightAgent 在 Execute 阶段执行每个 Step 的数据查询和洞察分析
- **inputs**: payload JSON（insight_type + query_config 三元组 + table_level）
- **outputs**: 结构化 JSON（含 filter_data / significance / description / chart_configs / found_entities）

## When to Use
- ✅ 执行洞察分析（OutstandingMin / Trend / Correlation 等 12 种函数）
- ✅ 纯三元组数据查询（不做分析，只拉数据）
- ❌ 查询 Schema（用 `insight_decompose`）
- ❌ NL2Code 自定义分析（用 `insight_nl2code`）

## How to Use

### 洞察函数执行（推荐路径）
```
get_skill_script(
    "insight_query",
    "run_insight.py",
    execute=True,
    args=["<payload_json_string>"]
)
```
payload：
```json
{
  "insight_type": "OutstandingMin",
  "query_config": {
    "dimensions": [[]],
    "breakdown": {"name": "portUuid", "type": "UNORDERED"},
    "measures": [{"name": "CEI_score", "aggr": "AVG"}]
  },
  "table_level": "day",
  "phase_id": 1,
  "step_id": 1,
  "phase_name": "定位低分PON口",
  "step_name": "找出 CEI_score 最低的 PON 口"
}
```

**带 IN 过滤的下钻调用**：
```json
{
  "insight_type": "OutstandingMin",
  "query_config": {
    "dimensions": [[{"dimension": {"name": "portUuid", "type": "DISCRETE"}, "conditions": [{"oper": "IN", "values": ["uuid-a", "uuid-b"]}]}]],
    "breakdown": {"name": "portUuid", "type": "UNORDERED"},
    "measures": [{"name": "ODN_score", "aggr": "AVG"}, {"name": "Wifi_score", "aggr": "AVG"}]
  },
  "table_level": "day"
}
```

### 返回格式
```json
{
  "status": "ok",
  "skill": "insight_query",
  "op": "run_insight",
  "insight_type": "OutstandingMin",
  "significance": 0.73,
  "description": {"min_group": "uuid-a", "summary": "..."},
  "filter_data": [{"portUuid": "uuid-a", "CEI_score": 54.08}, ...],
  "chart_configs": {"chart_type": "bar", "title": {...}, "series": [...]},
  "found_entities": {"portUuid": ["uuid-a", "uuid-b"]},
  "data_shape": [3857, 2],
  "phase_id": 1,
  "step_id": 1,
  "phase_name": "定位低分PON口",
  "step_name": "找出 CEI_score 最低的 PON 口"
}
```

**`chart_configs` 包含完整的 ECharts option JSON，Agent 必须原样保留，禁止改写。**

**每个 Phase 开始前**，必须先在 assistant 文本中输出 `phase_start` 事件（在第一次调用脚本之前）：
```
<!--event:phase_start-->
{"phase_id": 1, "name": "定位低分PON口", "status": "running"}
```

**每个 Step 脚本调用完成后**，必须在 assistant 文本中输出 `step_result` 事件：
```
<!--event:step_result-->
{"phase_id": 1, "step_id": 1, "insight_type": "OutstandingMin", "significance": 0.73, "summary": "CEI_score 最小值出现在 uuid-a（54.08）", "found_entities": {"portUuid": ["uuid-a", "uuid-b"]}, "status": "ok"}
```

> 🔴 **`step_result` 必须独立输出，不被 stdout 替代**：`run_insight.py` 的 stdout 由框架自动展示（图表渲染通道）；`step_result` 是独立的进度追踪信号，前端进度条依赖它。即使 stdout 已展示，每步执行后仍必须在 assistant 文本中输出 `step_result`，缺失会导致进度跟踪失败。`done` 事件同理。

### 纯数据查询
```
get_skill_script("insight_query", "run_query.py", execute=True, args=["<payload_json_string>"])
```

## Scripts
- `scripts/run_insight.py` — 三元组查询 + 12 种洞察函数（返回 chart_configs）
- `scripts/run_query.py` — 纯三元组查询（返回 records + summary）

## References
- `references/triple_schema.md` — 三元组格式契约

## 禁止事项
- ❌ 不得改写 `chart_configs`（必须原样透传）
- ❌ 不得改写 `filter_data` / `found_entities`（必须原样透传）
