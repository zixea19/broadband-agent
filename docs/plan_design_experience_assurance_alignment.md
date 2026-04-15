# 方案设计 & 体验保障模块对焦设计方案

> 创建时间：2026-04-15
> 涉及文件：5 个用户提交文件 + 本次对焦修改的 5 个上下游文件

---

## 一、问题诊断

### 1.1 方案格式不一致

| 层级 | 旧格式（已废弃） | 新格式（plan_design SKILL.md 已更新） |
|---|---|---|
| 段落标题 | `## WIFI 仿真方案` / `**启用**: true/false` | `AP补点推荐：` + 4空格缩进子字段 |
| 差异化承载段 | `切片类型` / `保障应用` / `白名单` / `带宽保障` | `差异化承载` / `应用类型` / `保障应用` / `业务类型` |
| 5段名称 | WIFI仿真方案/差异化承载方案/CEI配置方案/故障诊断方案/远程闭环处置方案 | AP补点推荐/CEI体验感知/故障诊断/远程优化/差异化承载 |

**受影响文件**：`prompts/planning.md` §5（硬编码旧格式）、`prompts/orchestrator.md` §4（旧字段判断条件）

### 1.2 experience_assurance.py 无法独立运行

当前文件是未完成的骨架（引用了未定义的 `parse_args`/`process_input_args`/`ExperienceAssuranceClient`），
无法作为独立 mock 运行，且 stdout 输出为人类可读进度日志，`event_adapter` 无法解析为 SSE 事件。

### 1.3 assurance_parameters.md 字段映射过时

当前映射表基于旧方案字段（`切片类型`/`白名单`/`带宽保障`），与
新 `plan_design` 差异化承载段（`应用类型`/`保障应用`/`业务类型`）不一致，
且与新脚本 CLI（`--application-type`/`--application`/`--business-type`）不对齐。

### 1.4 experience_assurance 无 SSE 渲染事件

脚本结果保存在文件 `output_dir/experience_assurance_output.json`，
`event_adapter` 未对该 skill 做专项渲染，前端无法展示体验保障配置结果表格。

---

## 二、变更范围（严格遵循职责边界）

```
Skills 层:
  skills/experience_assurance/scripts/experience_assurance.py  ← 重写为可运行 mock + stdout JSON
  skills/experience_assurance/references/assurance_parameters.md ← 对齐新3参数接口

Prompts 层:
  prompts/planning.md    ← §5 段名 + 格式描述对齐 plan_design SKILL.md
  prompts/orchestrator.md ← §4 差异化承载跳过条件字段名修正

API 层:
  api/event_adapter.py  ← 新增 experience_assurance_result SSE 事件

前端层（设计规范，需前端侧实现）:
  docs/experience_assurance_sse_spec.md ← 新 SSE 事件协议文档
```

---

## 三、experience_assurance.py 重写方案

### 3.1 设计原则

遵循 `simulate.py` 的 Pipeline/Tool Wrapper 模式：
- 解析 3 个 CLI 参数：`--application-type`、`--application`、`--business-type`
- 在真实 FAE 环境下调用 `NCELogin` + `ExperienceAssuranceClient`（保留 try/except 降级）
- demo/mock 环境下生成符合接口协议的 mock 结果数据
- **最终向 stdout 输出单行结构化 JSON**（与 simulate.py 的 `_ORIG_STDOUT.write` 模式一致）
- 同时保存 `output_dir/experience_assurance_output.json`（向后兼容）

### 3.2 stdout JSON 结构

```json
{
  "skill": "experience_assurance",
  "status": "ok",
  "business_type": "experience-assurance",
  "application_type": "anchor-video",
  "application": "TikTok",
  "result": {
    "taskId": "...",
    "neName": "200.30.33.63",
    "neIp": "200.30.33.63",
    "fsp": "0/3/2",
    "onuId": 5,
    "servicePortIndex": 0,
    "serviceName": "103/0_3_2/5/1/多业务VLAN模式/1",
    "configStatus": 0,
    "runningStatus": 1,
    "policyProfile": "defaultProfile",
    "limitProfile": "",
    "serviceType": "assure",
    "appCategory": "anchor-video",
    "appId": "...",
    "appName": "TikTok",
    "startTime": "2025-12-15 19:46:35",
    "timeLimit": -1
  },
  "output_file": "skills/experience_assurance/output_dir/experience_assurance_output.json"
}
```

错误路径：`{"skill": "experience_assurance", "status": "error", "message": "..."}`

---

## 四、SSE 事件协议：experience_assurance_result

### 4.1 事件触发条件

`api/event_adapter.py` 在 `ToolCallCompleted` 且 `skill_name == "experience_assurance"` 时触发，
解析 stdout JSON 的 `result` 字段，向前端推送 `experience_assurance_result` 事件。

### 4.2 事件 payload

```json
{
  "renderType": "experience_assurance",
  "renderData": {
    "businessType": "experience-assurance",
    "applicationType": "anchor-video",
    "application": "TikTok",
    "taskData": {
      "taskId": "b909cce2-7f68-4c89-9dd3-86017399d482",
      "neName": "200.30.33.63",
      "neIp": "200.30.33.63",
      "fsp": "0/3/2",
      "onuId": 5,
      "servicePortIndex": 3979,
      "serviceName": "103/0_3_2/5/1/多业务VLAN模式/1",
      "configStatus": 0,
      "runningStatus": 1,
      "policyProfile": "defaultProfile",
      "limitProfile": "",
      "serviceType": "assure",
      "appCategory": "anchor-video",
      "appId": "0f5cb694-f20a-4baa-b692-f904b29989ad",
      "appName": "TikTok",
      "startTime": "2025-12-15 19:46:35",
      "timeLimit": -1
    }
  }
}
```

### 4.3 前端渲染建议（表格）

| 字段 key | 显示标签 | 说明 |
|---|---|---|
| taskId | 任务 ID | UUID |
| neIp | 设备 IP | |
| fsp | 设备位置 | 框/槽/端口 |
| onuId | ONU ID | |
| servicePortIndex | 服务端口索引 | |
| configStatus | 配置状态 | 0=已配置 |
| runningStatus | 运行状态 | 1=运行中 |
| policyProfile | 策略配置 | |
| serviceType | 服务类型 | assure=体验保障 |
| appCategory | 应用类别 | |
| appName | 应用名称 | |
| startTime | 开始时间 | |
| timeLimit | 时间限制 | -1=无限制 |

建议以卡片 + 数据表格形式展示，标题行显示 `业务类型: {businessType}` 和 `保障应用: {application}`。
前端监听 SSE event name `experience_assurance_result`，提取 `data.renderData` 进行渲染。

---

## 五、assurance_parameters.md 更新要点

| 旧字段（废弃） | 新方案字段 | CLI 参数 | 允许值 |
|---|---|---|---|
| `切片类型` | `应用类型` | `--application-type` | anchor-video / real-time-game / cloud-platform / online-office |
| `保障应用` | `保障应用` | `--application` | TikTok / Kwai / 抖音 / 快手 等 |
| `白名单` + `带宽保障` + `切片策略` | `业务类型` | `--business-type` | experience-assurance / speed-limit / app-flow |

设备级参数（`--ne-id`/`--onu-res-id`/`--service-port-index`）现在由脚本内部 mock 处理，不再需要 Provisioning 传入。

---

## 六、prompts 修改要点

### planning.md §5
- 旧: `"WIFI 仿真方案 / 差异化承载方案 / CEI 配置方案 / 故障诊断方案 / 远程闭环处置方案"`
- 新: `"AP补点推荐 / CEI体验感知 / 故障诊断 / 远程优化 / 差异化承载"`
- 旧: `"每段**必须**含 **启用**: true/false 头"`
- 新: `"每段标题为 中文名称：格式，子字段 4 空格缩进，True/False 驱动启用"`

### orchestrator.md §4
- 旧: `"差异化wifi切片：False → 跳过 provisioning-delivery"`
- 新: `"差异化承载：False → 跳过 provisioning-delivery"`
