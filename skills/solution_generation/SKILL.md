---
name: solution_generation
description: "根据用户画像生成综合网络调优方案，包含 CEI、故障、远程闭环、Wifi 四类配置；支持综合目标和数据洞察两种输入模式"
---

# 方案生成

## Metadata
- **name**: solution_generation
- **description**: 依据用户画像渲染四类方案模板（CEI + 故障 + 远程闭环 + Wifi）
- **when_to_use**: slot_filling 完成后（综合目标 或 数据洞察模式），需要根据结构化画像生成完整调优方案时
- **paradigm**: Template + Workflow
- **inputs**: slot_filling 输出的结构化画像 JSON（含 mode 标记）
- **outputs**: 包含四类配置的完整方案（数据洞察模式额外含 optimization_focus 块）

## When to Use
- ✅ slot_filling 已完成，所有必填槽位已齐（模式A）
- ✅ 数据洞察后 slot_filling(data_insight 模式)完成，画像中含 `mode="data_insight"`（模式B）
- ❌ 槽位信息不完整时（应继续 slot_filling）
- ❌ 用户只需要单个配置（应用具体功能 Skill）

## 输入模式

### 模式A — 综合目标画像

- **来源**：slot_filling 模式A输出（标准槽位 JSON，无 `mode` 字段）
- **调用函数**：`render_all(profile_json)`
- **输出**：四类标准配置（CEI / 故障 / 远程闭环 / Wifi）

### 模式B — 数据洞察画像

- **来源**：slot_filling 模式B输出（含 `"mode": "data_insight"` 和 `config_hints`）
- **调用函数**：`render_from_insight(profile_json)`
- **输出**：四类标准配置 + `optimization_focus` 块
  - `optimization_focus` 包含 `priority_pons`、`distinct_issues`、`remote_loop_candidates` 等结构化洞察元数据
  - Agent 在最终回答中应结合 `optimization_focus` 描述方案的针对性和优先级

> **扩展点**：后续可将 `config_hints` 中的 `priority_pons` 直接注入 Jinja2 模板（如 CEI 模板的 `target_pon` 字段），实现精细化渲染。当前原型阶段模板使用通用画像字段。

## How to Use
1. 接收 slot_filling 输出的画像 JSON（字符串形式）
2. 调用 `get_skill_script("solution_generation", "render.py", execute=True)`，将完整画像 JSON 字符串作为唯一参数传入
   - **无需手动选择函数**：脚本自动检测 JSON 中的 `"mode"` 字段
     - `"mode": "data_insight"` → 内部调用 `render_from_insight`（输出含 `optimization_focus` 块）
     - 无 `mode` 字段 → 内部调用 `render_all`（标准四类配置）
3. 脚本根据画像参数渲染四类配置模板：
   - `references/cei_spark.yaml.j2` → CEI 配置
   - `references/fault_api.json.j2` → 故障配置
   - `references/remote_loop.json.j2` → 远程闭环配置
   - `references/wifi_sim.yaml.j2` → Wifi 仿真配置
4. 将四份配置（及 optimization_focus，若有）整合为完整方案展示给用户

## References
- `cei_spark.yaml.j2`
- `fault_api.json.j2`
- `remote_loop.json.j2`
- `wifi_sim.yaml.j2`

## Examples

### 模式A 示例

**输入画像**:
```json
{
  "user_type": "主播用户",
  "package_type": "直播套餐",
  "scenario": "卖场走播",
  "guarantee_target": "STA级",
  "time_window": "18:00-22:00"
}
```
**输出**: 包含四类配置的完整方案文档

### 模式B 示例

**输入画像**:
```json
{
  "mode": "data_insight",
  "user_type": "宽带用户",
  "guarantee_target": "整网",
  "time_window": "19:00-22:00",
  "config_hints": {
    "priority_pons": ["PON-2/0/5", "PON-1/0/3"],
    "distinct_issues": ["带宽利用率过高", "丢包率超标"],
    "remote_loop_candidates": ["PON-2/0/5"]
  }
}
```
**输出**: 四类标准配置 + optimization_focus（含 priority_pons、distinct_issues 等）
