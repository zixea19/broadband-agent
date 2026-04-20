---
name: insight_reflect
description: "Phase 反思决策：每个 Phase 执行完后评估结果，决定 A继续/B修改/C插入/D跳过"
---

# Phase 反思

## Metadata
- **paradigm**: Instructional
- **when_to_use**: InsightAgent 完成一个 Phase 的所有 Step 后，评估结果并决定后续 Phase 如何调整
- **inputs**: 当前 Phase 的 step_results + remaining_phases
- **outputs**: 反思决策 JSON（choice + reason + 更新后的 remaining_phases）

## When to Use
- ✅ 每个 Phase 的所有 Step 执行完毕后，**无论是否还有后续 Phase，都必须输出**
- 最后一个 Phase：choice 固定 `"A"`，`next_phase` 填 `null`

## How to Use

1. 加载反思规则：`get_skill_reference("insight_reflect", "reflect_rubric.md")`
2. 评估当前 Phase 的 step_results
3. 🔴 **必须**在 assistant 消息中输出反思决策（前端进度追踪依赖此事件，缺失会导致跟踪失败）：

```
<!--event:reflect-->
{"phase_id": 1, "choice": "A", "reason": "成功识别低分PON口，按原计划进入Phase 2", "next_phase": 2}
```

最后一个 Phase 示例：
```
<!--event:reflect-->
{"phase_id": 4, "choice": "A", "reason": "所有 Phase 分析完成，进入 Report 阶段", "next_phase": null}
```

## 4 种决策

| 选项 | 含义 | 何时使用 |
|---|---|---|
| **A** | 继续原计划 | 结果符合预期 |
| **B** | 修改下一 Phase 的 milestone/description | 发现意外方向，需要调整 |
| **C** | 在下一 Phase 前插入新 Phase | 需要补充中间分析步骤 |
| **D** | 跳过某个后续 Phase | 已直接得出结论，无需继续 |

## References
- `references/reflect_rubric.md` — A/B/C/D 决策规则 + JSON 输出格式

## 禁止事项
- ❌ 反思阶段不调脚本、不查数据
- ❌ 根因分析类任务禁止轻易选 D 跳过 L3/L4
- ❌ 反思失败时保持原计划继续执行，不要进入死循环
