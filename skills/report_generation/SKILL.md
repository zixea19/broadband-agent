---
name: report_generation
description: "聚合分析结果或方案配置，渲染为结构化 Markdown 报告"
---

# 报告生成

## Metadata
- **name**: report_generation
- **description**: 聚合结果渲染 Markdown 报告
- **when_to_use**: 方案生成完成后 或 数据洞察分析完成后，需要生成汇总报告
- **paradigm**: Template + Workflow
- **inputs**: 方案配置 或 分析结果（JSON 格式）
- **outputs**: Markdown 格式报告

## When to Use
- ✅ 综合目标流程的最后一步，汇总所有配置
- ✅ 数据洞察完成后生成分析报告
- ❌ 流程中间步骤，不需要报告

## How to Use

**数据洞察模式**（来自 data_insight 输出）：
1. 将 `mock_query.py` 的完整 JSON 输出字符串准备好（即 `get_skill_script` 返回的 `stdout` 字段内容）
2. 调用 `get_skill_script("report_generation", "render_report.py", execute=True, args="--insight <insight_json>")`
3. 将返回的 `stdout` Markdown 内容直接展示给用户

**综合目标模式**（来自 solution_generation 输出）：
1. 构建上下文 JSON：`{"title": "...", "profile": {...}, "configs": {...}, "verification": {...}}`
2. 调用 `get_skill_script("report_generation", "render_report.py", execute=True, args="<context_json>")`
3. 将返回的 `stdout` Markdown 内容直接展示给用户

**禁止**：不要基于模板自行生成报告文本，必须通过脚本渲染。

> ⚠️ **CRITICAL — 输出规则**：`render_report.py` 的 `stdout` 即为完整报告，**必须原样复制到最终回答**。任何基于报告内容的二次改写、摘要、重排均被视为违规，不论改写后格式是否更美观。

## Scripts
- `scripts/render_report.py` — Jinja2 模板渲染脚本，接受上下文 JSON，输出 Markdown

## References
- `references/report.md.j2` — Markdown 报告 Jinja2 模板（由脚本加载，无需手动读取）

## Examples

**数据洞察模式输入**: `mock_query.py` 的完整 JSON 输出
**综合目标模式输入**: `{"profile": {...}, "configs": {...}, "verification": {...}}`
**输出**: 结构化 Markdown 报告
