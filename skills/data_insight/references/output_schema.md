# 数据洞察 Skills 输出数据契约

> 供前端开发参考。数据洞察流程有两类输出通道：
> 1. **脚本 stdout**：通过 agno ToolCallCompleted 事件推送，包含查询结果、洞察分析、ECharts 图表
> 2. **InsightAgent assistant 文本**：包含阶段事件标记（`<!--event:xxx-->`），用于渲染流程进度和最终报告

---

## 端到端事件流（按时间顺序）

前端从 InsightAgent 的 assistant 文本中解析 `<!--event:xxx-->` 标记，获取流程级事件：

```
用户输入 "分析PON口CEI下降原因"
  ↓
<!--event:plan-->              ← 阶段规划（含所有 Phase 概览）
  ↓
for each Phase:
  ├─ <!--event:phase_start-->  ← Phase 开始
  ├─ [ToolCall] run_insight.py / run_nl2code.py  ← 脚本执行（1-8 次）
  ├─ <!--event:step_result-->  ← 每个 Step 执行后的精简摘要（1-8 次）
  └─ <!--event:reflect-->      ← Phase 结束反思决策
  ↓
<!--event:report-->            ← 完整报告（含所有 Phase 的 Steps + Charts + Summary）
<!--event:done-->              ← 流程结束信号
```

### event:plan — 阶段规划
```json
<!--event:plan-->
{
  "goal": "找出 CEI 分数较低的 PON 口并分析原因",
  "total_phases": 4,
  "phases": [
    {"phase_id": 1, "name": "L1-定位低分PON口", "milestone": "识别CEI最低的PON口列表", "table_level": "day"},
    {"phase_id": 2, "name": "L2-维度归因扫描", "milestone": "确定哪个维度拖分", "table_level": "day"},
    {"phase_id": 3, "name": "L3-根因指标定位", "milestone": "找到维度内具体异常指标", "table_level": "day"},
    {"phase_id": 4, "name": "L4-时序下钻验证", "milestone": "验证根因指标时序分布", "table_level": "minute"}
  ]
}
```
**前端渲染**：展示分析阶段概览（如步骤条/时间线），让用户知道接下来要做什么。

### event:phase_start — Phase 开始
```json
<!--event:phase_start-->
{"phase_id": 1, "name": "L1-定位低分PON口", "milestone": "识别CEI最低的PON口列表", "table_level": "day", "status": "running"}
```
**前端渲染**：高亮当前执行的 Phase（步骤条进度更新）。

### event:step_result — Step 执行结果摘要
```json
<!--event:step_result-->
{
  "phase_id": 1,
  "step_id": 1,
  "insight_type": "OutstandingMin",
  "significance": 0.73,
  "summary": "CEI_score 最小值出现在 288b6c71-...（54.08），z-score=5.36",
  "found_entities": {"portUuid": ["288b6c71-...", "1c86d285-..."]}
}
```
**前端渲染**：步骤卡片（标题=insight_type，正文=summary，标签=significance）。
**注意**：完整的 `chart_configs` 和 `filter_data` 在对应的 ToolCallCompleted 事件的脚本 stdout 里（`op: "run_insight"`），前端需要关联 `phase_id + step_id` 来匹配。

### event:reflect — Phase 反思决策
```json
<!--event:reflect-->
{"phase_id": 1, "choice": "A", "reason": "成功识别低分PON口，按原计划进入Phase 2", "next_phase": 2}
```
| choice | 含义 |
|---|---|
| A | 继续原计划 |
| B | 修改下一 Phase |
| C | 插入新 Phase |
| D | 跳过后续 Phase |

**前端渲染**：Phase 完成标记 + 反思结果标签。

### event:report — 完整报告
```json
<!--event:report-->
{
  "title": "CEI 低分 PON 口根因分析报告",
  "goal": "找出 CEI 分数较低的 PON 口并分析原因",
  "phases": [
    {
      "phase_id": 1,
      "name": "L1-定位低分PON口",
      "milestone": "识别CEI最低的PON口列表",
      "table_level": "day",
      "steps": [
        {
          "step_id": 1,
          "insight_type": "OutstandingMin",
          "significance": 0.73,
          "summary": "CEI_score 最小值出现在 288b6c71-...（54.08），z-score=5.36",
          "found_entities": {"portUuid": ["288b6c71-...", "1c86d285-..."]},
          "chart_configs": { "chart_type": "bar", ... }
        }
      ],
      "reflection": {"choice": "A", "reason": "..."}
    }
  ],
  "summary": {
    "goal": "找出 CEI 分数较低的 PON 口并分析原因",
    "priority_pons": ["uuid-a", "uuid-b"],
    "priority_gateways": [],
    "distinct_issues": ["Rate_score 极低", "Service_score 偏低"],
    "scope_indicator": "multi_pon",
    "peak_time_window": null,
    "has_complaints": false,
    "remote_loop_candidates": [],
    "root_cause_fields": ["rxTrafficPercent", "meanRxRatePercent"],
    "reflection_log": [
      {"phase": 1, "choice": "A", "reason": "..."},
      {"phase": 2, "choice": "A", "reason": "..."}
    ]
  }
}
```
**前端渲染**：完整的多阶段报告页面（每个 Phase 一个区块，每个 Step 一个卡片 + ECharts 图表）。

### event:done — 流程结束
```json
<!--event:done-->
{"total_phases": 4, "total_steps": 12, "total_charts": 8}
```
**前端渲染**：进度条完成 + 统计摘要。

---

## 脚本 stdout 输出格式（通过 ToolCallCompleted 事件推送）

以下是每个脚本通过 stdout 输出的 JSON 格式。前端通过 JSON 中的 `op` 字段区分来源。

---

## 1. list_schema.py — Schema 查询

**触发时机**：InsightAgent 在 Decompose 阶段查询天表/分钟表的可用字段

**前端用途**：可选展示，一般不需要渲染

```json
{
  "status": "ok",
  "skill": "data_insight",
  "op": "list_schema",
  "table": "day",
  "focus_dimensions": ["ODN"],
  "schema_markdown": "## 核心分组字段\n- portUuid ...",
  "all_fields": ["CEI_score", "ODN_score", ...]
}
```

---

## 2. run_query.py — 纯数据查询

**触发时机**：InsightAgent 需要拉原始数据但不做洞察分析

**前端用途**：可选，一般作为中间步骤

```json
{
  "status": "ok",
  "skill": "data_insight",
  "op": "run_query",
  "fixed_query_config": { ... },
  "fix_warnings": ["字段替换: 'xxx' → 'yyy'"],
  "data_shape": [3857, 10],
  "columns": ["portUuid", "CEI_score", ...],
  "records": [
    {"portUuid": "uuid-a", "CEI_score": 54.08, ...},
    ...
  ],
  "summary": "数据行数：3857，CEI_score：最大=100.000, 最小=54.080 ..."
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| records | array | 最多 50 条记录 |
| columns | array | 列名列表 |
| data_shape | [int, int] | [行数, 列数] |
| summary | string | 文字摘要 |

---

## 3. run_insight.py — 洞察函数执行（核心）

**触发时机**：InsightAgent 对每个分析步骤调用 12 种洞察函数之一

**前端用途**：⭐ 核心渲染对象 — 每次调用对应一个分析步骤的结果

```json
{
  "status": "ok",
  "skill": "data_insight",
  "op": "run_insight",
  "insight_type": "OutstandingMin",
  "significance": 0.73,
  "description": {
    "min_group": "288b6c71-...",
    "min_value": 54.08,
    "second_value": 55.42,
    "gap": 1.34,
    "z_score": 5.36,
    "summary": "CEI_score 最小值出现在 288b6c71-...（54.08），低于第二名 1.34，z-score=5.36"
  },
  "filter_data": [
    {"portUuid": "288b6c71-...", "CEI_score": 54.08},
    {"portUuid": "1c86d285-...", "CEI_score": 55.42},
    ...
  ],
  "chart_configs": {
    "chart_type": "bar",
    "title": {"text": "CEI_score 最小值分析 (Top10)", ...},
    "tooltip": {...},
    "grid": {...},
    "xAxis": {"type": "category", "data": [...]},
    "yAxis": {"type": "value", "name": "CEI_score"},
    "series": [{"type": "bar", "data": [...]}]
  },
  "fix_warnings": [],
  "found_entities": {
    "portUuid": ["288b6c71-...", "1c86d285-...", ...]
  },
  "data_shape": [3857, 2],
  "value_columns_used": ["CEI_score"],
  "group_column_used": "portUuid"
}
```

### 关键字段说明

| 字段 | 类型 | 前端怎么用 |
|---|---|---|
| `insight_type` | string | 标识洞察类型，可作为步骤卡片标题。12 种可选值见下表 |
| `significance` | float [0, 1] | 结果显著性。>= 0.5 高亮，< 0.3 可折叠 |
| `description` | string 或 dict | dict 时取 `.summary` 字段作为文字描述 |
| `filter_data` | array[dict] | 最多 50 条，可渲染为表格 |
| `chart_configs` | dict | **完整的 ECharts option**，前端直接传给 `echarts.setOption()` 即可 |
| `found_entities` | dict | 下钻实体，如 `{"portUuid": [...]}`，可作为关联标签展示 |
| `data_shape` | [int, int] | 查询结果的完整行列数（filter_data 是截断后的） |
| `fix_warnings` | array[string] | 三元组自动修复的警告信息 |

### 12 种 insight_type

| insight_type | chart_type | 说明 |
|---|---|---|
| OutstandingMin | bar | 找最低值 |
| OutstandingMax | bar | 找最高值 |
| OutstandingTop2 | bar | 找前两名 |
| Trend | line | 线性回归趋势 |
| ChangePoint | line + markLine | 时序变点检测 |
| Seasonality | line | 周期性检测 |
| OutlierDetection | scatter | 异常点检测 |
| Correlation | scatter | 两指标相关性 |
| CrossMeasureCorrelation | heatmap | 多指标交叉相关 |
| Clustering | scatter | KMeans 聚类 |
| Attribution | pie/bar | 贡献度归因 |
| Evenness | bar | 均匀度分析 |

---

## 4. run_nl2code.py — NL2Code 沙箱执行

**触发时机**：InsightAgent 需要自定义 pandas 分析（如 Top N 查询、多列比较）

**前端用途**：步骤结果展示（类似 run_insight 但没有 chart_configs）

```json
{
  "status": "ok",
  "skill": "data_insight",
  "op": "run_nl2code",
  "result": {
    "type": "dataframe",
    "shape": [5, 10],
    "columns": ["portUuid", "CEI_score", ...],
    "records": [
      {"portUuid": "288b6c71-...", "CEI_score": 54.08, ...}
    ]
  },
  "description": "NL2Code 分析完成 — 筛选 5 个低分 PON 口；结果 5 行 x 10 列",
  "fix_warnings": [],
  "data_shape": [3857, 10],
  "code": "target_ports = [...]\nresult = df[df['portUuid'].isin(target_ports)]..."
}
```

### result 的 type 变体

| type | 字段 | 说明 |
|---|---|---|
| `"dataframe"` | shape, columns, records | DataFrame 结果（最常见） |
| `"dict"` | value | 字典结果 |
| `"list"` | value | 列表结果 |
| `"scalar"` | text | 标量/字符串结果 |
| `"none"` | — | result 未赋值 |

---

## 5. render_report.py — 报告渲染

**触发时机**：InsightAgent 完成所有 Phase 后生成最终报告

**前端用途**：⭐ 最终报告渲染

**注意**：当前 agno 的 args 类型校验问题导致此脚本经常调用失败，InsightAgent 会兜底在 assistant 文本中直接输出 Markdown 报告。

成功时输出**纯 Markdown 文本**（不是 JSON）：
```markdown
# CEI 低分 PON 口根因分析报告

## 执行摘要
| 项目 | 内容 |
|------|------|
| 分析目标 | 找出 CEI 分数较低的 PON 口并分析原因 |
| 低分端口数量 | 10 个 |
...

## Phase 1: L1 - 低分 PON 口识别
...
```

---

## 6. 错误格式（所有脚本通用）

```json
{
  "status": "error",
  "skill": "data_insight",
  "op": "run_insight",
  "error": "错误描述信息"
}
```

前端遇到 `status: "error"` 时应展示错误提示。

---

## 7. 通过 tool_name 区分数据来源

agno 推送给前端的 ToolCallCompleted 事件中包含 `tool_name`（即 `get_skill_script`），
前端可通过事件中的 `script_path` 或 stdout JSON 的 `op` 字段区分：

| op 值 | 对应脚本 | 前端渲染方式 |
|---|---|---|
| `list_schema` | list_schema.py | 可忽略或折叠 |
| `run_query` | run_query.py | 数据表格（可折叠） |
| `run_insight` | run_insight.py | **步骤卡片 + ECharts 图表** |
| `run_nl2code` | run_nl2code.py | 数据表格 + 代码展示 |

## 8. InsightAgent 文本输出（非脚本）

除了脚本 stdout，InsightAgent 还会在 assistant 文本中输出：

### 结构化交接契约（JSON 代码块）
```json
{
  "summary": {
    "goal": "分析目标",
    "priority_pons": ["uuid-a", "uuid-b"],
    "distinct_issues": ["问题1", "问题2"],
    "scope_indicator": "single_pon" | "multi_pon" | "regional",
    "peak_time_window": "19:00-22:00" | null,
    "has_complaints": false,
    "root_cause_fields": ["rxTrafficPercent", ...],
    "reflection_log": [{"phase": 1, "choice": "A", "reason": "..."}]
  }
}
```

### 指针陈述（纯文本）
```
✅ 查询到 5 个低 CEI PON 口，主要根因为上行流量异常...
```
