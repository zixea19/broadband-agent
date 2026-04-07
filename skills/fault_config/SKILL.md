---
name: fault_config
description: "生成故障配置 API 参数，用于网络故障检测与自动化处置策略配置"
---

# 故障配置生成

## Metadata
- **name**: fault_config
- **description**: 生成故障 API 配置，用于故障检测与处置策略
- **when_to_use**: 用户要求配置故障检测策略 / 故障 API / 故障处置配置时
- **paradigm**: Template + Reference
- **inputs**: 故障场景和处置策略参数
- **outputs**: JSON 格式的故障配置

## When to Use
- ✅ 用户说"故障配置"、"故障 API"、"故障策略"、"故障检测"
- ✅ 综合目标流程中需要故障子配置
- ❌ 用户在报告实际故障（应转人工）

## How to Use
1. 调用 `get_skill_reference("fault_config", "default_fault.json")` 加载默认配置模板
2. 展示默认配置
3. 根据用户场景调整参数
4. 生成最终配置

## References
- `default_fault.json` — 默认故障配置模板

## Examples

**输入**: "配置故障检测，关注光功率异常和丢包"
**输出**: 包含对应检测规则的 JSON 配置
