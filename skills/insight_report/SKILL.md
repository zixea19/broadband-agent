---
name: insight_report
description: "洞察报告生成：汇总所有 Phase 的分析结果，渲染 Markdown 报告 + 结构化交接契约"
---

# 洞察报告

## Metadata
- **paradigm**: Generator
- **when_to_use**: InsightAgent 完成所有 Phase 后，汇总生成最终报告
- **inputs**: 所有 Phase 的 step_results + reflection_log
- **outputs**: Markdown 报告 + 结构化交接契约 JSON

## When to Use
- ✅ 所有 Phase 执行完毕，需要生成最终报告
- ❌ 还有未完成的 Phase（先完成再出报告）

## How to Use

### 方式 1 — 调用渲染脚本
```
get_skill_script(
    "insight_report",
    "render_report.py",
    execute=True,
    args=["<context_json_string>"]
)
```
脚本 stdout 是渲染好的 Markdown，**必须原样输出，禁止改写**。

### 方式 2 — 兜底（脚本调用失败时）
直接在 assistant 消息中用 Markdown 输出报告，包含：
- 各 Phase 的步骤结果表格
- 关键发现总结
- 结构化交接契约 JSON

### 最终输出事件
**无论用哪种方式**，都必须在 assistant 消息末尾输出：

```json
<!--event:report-->
{
  "title": "CEI 低分 PON 口根因分析报告",
  "goal": "找出 CEI 分数较低的 PON 口并分析原因",
  "phases": [
    {
      "phase_id": 1,
      "name": "L1-定位低分PON口",
      "steps": [{"step_id": 1, "insight_type": "OutstandingMin", "significance": 0.73, "summary": "...", "chart_configs": {...}}],
      "reflection": {"choice": "A", "reason": "..."}
    }
  ],
  "summary": {
    "priority_pons": ["uuid-a"],
    "distinct_issues": ["Rate_score 极低"],
    "root_cause_fields": ["rxTrafficPercent"],
    "scope_indicator": "multi_pon",
    "reflection_log": [{"phase": 1, "choice": "A", "reason": "..."}]
  }
}
```

然后输出结束信号：
```json
<!--event:done-->
{"total_phases": 4, "total_steps": 12, "total_charts": 8}
```

## Scripts
- `scripts/render_report.py` — Jinja2 模板渲染 Markdown 报告

## References
- `references/output_schema.md` — 端到端数据契约（供前端开发参考）
- `references/multi_phase_report.md.j2` — 多阶段报告 Jinja2 模板
- `references/report.md.j2` — 归因报告 Jinja2 模板（旧版兼容）

## 禁止事项
- ❌ 不得改写 render_report.py 的 stdout
- ❌ 报告完成后禁止自动进入 Planning（必须等用户确认）
