---
name: remote_loop
description: "生成远程闭环配置，用于网络问题的远程自动化诊断与修复闭环"
---

# 远程闭环配置生成

## Metadata
- **name**: remote_loop
- **description**: 生成远程闭环配置，实现问题自动诊断→修复→验证闭环
- **when_to_use**: 用户要求配置远程闭环 / 远程诊断 / 自动修复流程时
- **paradigm**: Template + Reference
- **inputs**: 闭环场景和策略参数
- **outputs**: JSON 格式的远程闭环配置

## When to Use
- ✅ 用户说"远程闭环"、"远程诊断"、"闭环配置"、"自动修复"
- ✅ 综合目标流程中需要远程闭环子配置
- ❌ 用户在进行手动诊断操作

## How to Use
1. 调用 `get_skill_reference("remote_loop", "default_loop.json")` 加载默认配置模板
2. 展示默认闭环流程配置
3. 根据用户需求调整
4. 生成最终配置

## References
- `default_loop.json` — 默认远程闭环配置

## Examples

**输入**: "配置一个远程闭环，针对用户投诉网速慢的场景"
**输出**: 包含诊断→修复→验证步骤的 JSON 配置
