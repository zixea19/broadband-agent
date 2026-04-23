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

### Phase 批量执行（Execute 阶段主路径）
```
get_skill_script(
    "insight_query",
    "run_phase.py",
    execute=True,
    args=["<phase_payload_json_string>"]
)
```
payload 字段：`phase_id`、`phase_name`、`table_level`、`steps[]`（含 `step_id`、`step_name`、`insight_type`、`query_config`）：
```json
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
    },
    {
      "step_id": 2,
      "step_name": "分析 CEI 随时间的变化",
      "insight_type": "Trend",
      "query_config": { "...": "..." }
    }
  ]
}
```

返回的 `results[]` 按 `step_id` 顺序排列，每项格式与单步结果一致。

> NL2Code 类型的 step 仍走 `run_nl2code.py`，不放进 `run_phase.py`。
> 如果某 Phase 混有 NL2Code step，先调 `run_phase.py` 处理标准 step，再单独调 `run_nl2code.py`。


### 返回格式
```json
{
  "status": "ok",
  "skill": "insight_query",
  "op": "run_phase",
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

**`run_phase.py` 返回后**，从 `results[]` 逐步读取，对每个 result 在同一次回复内连续输出 `step_result` 事件：
```
<!--event:step_result-->
{"phase_id": 1, "step_id": 1, "insight_type": "OutstandingMin", "significance": 0.73, "summary": "CEI_score 最小值出现在 uuid-a（54.08）", "found_entities": {"portUuid": ["uuid-a", "uuid-b"]}, "status": "ok"}
```

> 🔴 **`step_result` 必须独立输出，不被 stdout 替代**：`run_phase.py` 的 stdout 由框架自动展示（图表渲染通道）；`step_result` 是独立的进度追踪信号，前端进度条依赖它。`run_phase.py` 返回后，必须在同一次回复内对每个 result 连续输出对应的 `step_result`，缺失会导致进度跟踪失败。`done` 事件同理。

### 纯数据查询
```
get_skill_script("insight_query", "run_query.py", execute=True, args=["<payload_json_string>"])
```

## Scripts
- `scripts/run_phase.py` — Phase 内所有标准 Step 批量执行（单次工具调用替代 N 次）
- `scripts/run_insight.py` — 内部依赖，由 run_phase.py 直接调用，LLM 不直接使用
- `scripts/run_query.py` — 纯三元组查询（返回 records + summary）

## References
- `references/triple_schema.md` — 三元组格式契约

## 禁止事项
- ❌ 不得改写 `chart_configs`（必须原样透传）
- ❌ 不得改写 `filter_data` / `found_entities`（必须原样透传）
