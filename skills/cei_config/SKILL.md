---
name: cei_config
description: "生成 CEI (Customer Experience Index) Spark 配置，用于网络质量体验指标的采集与评估配置"
---

# CEI 配置生成

## Metadata
- **name**: cei_config
- **description**: 生成 CEI Spark 配置，用于网络质量体验指标的采集与评估
- **when_to_use**: 用户明确要求生成 CEI 配置 / CEI Spark 配置 / 体验指标配置时
- **paradigm**: Template + Reference
- **inputs**: 用户指定的配置参数（可选，未指定则使用默认值）
- **outputs**: YAML 格式的 CEI Spark 配置

## When to Use
- ✅ 用户说"生成 CEI 配置"、"配置 CEI Spark"、"体验指标配置"
- ✅ 综合目标流程中 solution_generation 需要 CEI 子配置
- ❌ 用户只是问"什么是 CEI"（直接回答即可）
- ❌ 用户要求分析 CEI 数据（应使用 data_insight）

## How to Use
1. 调用 `get_skill_reference("cei_config", "default_cei.yaml")` 加载默认配置模板
2. 展示默认配置给用户，高亮可修改字段
3. 等待用户确认或指定修改
4. 应用用户修改，生成最终配置
5. 可选：调用 downstream dispatch 下发配置

## References
- `default_cei.yaml` — 默认 CEI Spark 配置模板

## Examples

**输入**: "帮我生成一个 CEI 配置，针对 PON-1/0/1 端口"
**输出**:
```yaml
cei_spark:
  target_pon: "PON-1/0/1"
  collection_interval: 300
  metrics:
    - bandwidth_utilization
    - packet_loss_rate
    - latency_avg
  threshold:
    cei_score_warning: 70
    cei_score_critical: 50
```
