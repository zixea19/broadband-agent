---
name: wifi_simulation
description: "生成 Wifi 无线仿真配置，用于模拟和评估无线网络覆盖与性能"
---

# Wifi 仿真配置生成

## Metadata
- **name**: wifi_simulation
- **description**: 生成 Wifi 仿真配置，模拟评估无线网络覆盖与性能
- **when_to_use**: 用户要求 Wifi 仿真 / 无线仿真 / Wifi 模拟配置时
- **paradigm**: Template + Reference
- **inputs**: 仿真场景参数
- **outputs**: YAML 格式的 Wifi 仿真配置

## When to Use
- ✅ 用户说"Wifi 仿真"、"无线仿真配置"、"Wifi 模拟"
- ✅ 综合目标流程中需要 Wifi 仿真子配置
- ❌ 用户只是问 Wifi 相关概念

## How to Use
1. 调用 `get_skill_reference("wifi_simulation", "default_wifi.yaml")` 加载默认配置模板
2. 展示默认配置，说明可调参数
3. 根据用户需求修改参数
4. 生成最终仿真配置

## References
- `default_wifi.yaml` — 默认 Wifi 仿真配置

## Examples

**输入**: "帮我做个 Wifi 仿真，3 室 1 厅户型"
**输出**: 基于户型参数生成的仿真配置 YAML
