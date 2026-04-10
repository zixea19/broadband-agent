# 家宽网络调优智能助手

基于 [agno](https://github.com/agno-agi/agno) 框架构建的家宽网络调优场景多智能体系统，采用 **Team (coordinate 模式) + 10 个业务 Skills** 的分层架构。

## 功能特性

支持三类任务入口：

1. **综合目标** — 用户描述业务目标，PlanningAgent 追问画像 → 产出分段方案 → 并行派发多个 Provisioning 实例执行
2. **数据洞察** — InsightAgent 按 4 阶段产出数据 / 归因 / ECharts 图表 / Markdown 报告，结果可回流 Planning 生成优化方案
3. **单点功能** — Orchestrator 关键词路由直达对应 Provisioning 实例（WIFI 仿真 / 差异化承载 / 故障定界 / 远程操作）

## 架构

```
OrchestratorTeam (leader, coordinate 模式)
  ├─ PlanningAgent            (goal_parsing + plan_design + plan_review)
  ├─ InsightAgent             (data_insight + report_rendering)
  ├─ ProvisioningWifiAgent    (wifi_simulation)              ← 单 Skill 内部 4 步
  ├─ ProvisioningDeliveryAgent (differentiated_delivery)
  └─ ProvisioningCeiChainAgent (cei_pipeline + fault_diagnosis + remote_optimization)
                                                             ← 条件串行 workflow
```

3 个 Provisioning 实例**共享** `prompts/provisioning.md`，通过 `description` 字段注入各自的功能目标。

### 业务 Skill 设计模式

- **`plan_design`**：Instructional 范式 — 纯 SKILL.md + few-shot 样例，**无脚本**，由 LLM 直接生成分段 Markdown 方案
- **`cei_pipeline / remote_optimization`**：Tool Wrapper 范式 — 封装 FAE 平台真实接口，CLI args 驱动，依赖 `fae_poc/` 共享的 NCELogin + config.ini
- **`fault_diagnosis / differentiated_delivery`**：Generator 范式 — SKILL.md 声明参数 schema，Jinja2 模板纯参数填空，**无业务规则分支**（业务规则已上移到 PlanningAgent）
- **`goal_parsing / plan_review`**：Inversion + Reviewer — 有状态/确定性任务保留脚本
- **`data_insight`**：按阶段（`query` / `attribution`）产出 ECharts option，透传给前端直接渲染
- **`wifi_simulation`**：Pipeline — 单脚本内部自驱 4 步（户型图识别 → 热力图 → RSSI → 选点对比）

## 技术栈

- Python 3.11 + agno >= 2.5.14
- Gradio (Web UI)
- loguru (应用日志) + SQLite (会话持久化与业务追踪)
- Jinja2 (配置模板渲染)

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 设置 API Key
export OPENAI_API_KEY="your-api-key"

# 启动应用
python ui/app.py
```

访问 http://localhost:7860 开始使用。

## 项目结构

```
├── configs/
│   ├── model.yaml          # 模型 provider/endpoint
│   ├── agents.yaml         # Team + 5 个 SubAgent 配置
│   └── downstream.yaml     # 下游系统 mock/real 切换
├── prompts/
│   ├── orchestrator.md     # Team leader 作业手册
│   ├── planning.md         # PlanningAgent 作业手册
│   ├── insight.md          # InsightAgent 作业手册
│   └── provisioning.md     # 3 个 Provisioning 实例共享的作业手册
├── skills/                 # 10 个业务 Skill (LocalSkills 自动扫描)
│   ├── goal_parsing/       # 槽位追问引擎
│   ├── plan_design/        # 方案设计 (Instructional, 无脚本)
│   ├── plan_review/        # 方案评审 (violations + recommendations)
│   ├── cei_pipeline/       # CEI 权重配置下发 (Tool Wrapper, 对接 FAE 真实接口)
│   ├── fault_diagnosis/    # 故障诊断配置
│   ├── remote_optimization/# 远程优化动作 (Tool Wrapper, 对接 FAE 真实接口)
│   ├── differentiated_delivery/ # 差异化承载 (切片/Appflow)
│   ├── wifi_simulation/    # WIFI 4 步仿真
│   ├── data_insight/       # 数据查询 + 归因 + ECharts
│   └── report_rendering/   # Markdown 报告渲染
├── core/
│   ├── agent_factory.py    # create_team() — 装配 Team + 5 SubAgent
│   ├── session_manager.py  # session_hash → Team + Tracer 隔离
│   ├── model_loader.py     # 模型实例化 + prompt tracer 注入
│   ├── downstream_client.py # mock/real 双模式客户端
│   └── observability/      # SQLite DAO + loguru sink + JSONL tracer
├── ui/
│   ├── app.py              # Gradio 入口 (Team 流式事件处理)
│   └── chat_renderer.py    # SubAgent 徽章 + 工具调用折叠渲染
└── tests/test_smoke.py     # 20 项冒烟测试
```

## 配置说明

- `configs/model.yaml` — 模型 provider / endpoint / role_map
- `configs/agents.yaml` — Team + 5 个 SubAgent 的 prompt + skills 子集 + description + memory
- `configs/downstream.yaml` — 下游系统 mock/real 切换
- `skills/goal_parsing/references/slot_schema.yaml` — 综合目标槽位定义
- `skills/plan_design/references/examples.md` — 方案设计 few-shot 样例

## 测试

```bash
pytest tests/test_smoke.py -v
```

20 项测试覆盖配置加载、Skill 脚本执行、Team 装配、可观测性。
