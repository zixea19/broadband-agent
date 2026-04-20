# CLAUDE.md

## 项目概述

家宽网络调优智能助手。基于 agno 框架的 Team (coordinate 模式) 多智能体系统：1 个 Orchestrator + 5 个 SubAgent + 16 个业务 Skills，覆盖从意图识别到配置下发的完整流程。**完整架构、目录结构、任务流程见 README.md。**

## 工作原则

**先理解，再动手**：修改前先读懂相关模块的职责边界。不清楚时明确说出假设，而不是静默推测后直接改代码。

**精准修改，不越界**：每次修改只触碰与任务直接相关的层，不顺手重构周边代码：
- Skills 修改 → 只改 `skills/<name>/`（SKILL.md / scripts / references）
- Agent 行为修改 → 只改 `prompts/` 或 `configs/agents.yaml`
- 可观测性修改 → 只改 `core/observability/`
- 数据层修改 → 只改 DB schema 和 repository
- API 层修改 → 只改 `api/`（为 huangxn27/broadband-agent-demo 前端服务的 FastAPI 后端）
- 前端修改 → 只改 `ui/`（Gradio 内嵌 UI）

**不为未来写代码**：不添加"将来可能用到"的抽象、开关或兼容层；三处相似代码优于一个过早的封装。

**每步可验证**：修改后执行 `uv run pytest tests/test_smoke.py -v` 确认无回归，再进入下一步。

## 架构关键边界

这些边界是修改时的硬约束，违反会破坏系统一致性：

- **决策型 Agent（Planning / Insight）** — 产出方案或报告，**不执行 Provisioning 级操作**
- **执行型 Agent（Provisioning × 3）** — 接收载荷后按 SKILL.md schema 提参调用，**不做业务规则判断**
- **Orchestrator** — 负责意图识别 + 路由 + 方案拆分 + 派发，**不推导 Skill 参数**（参数提取是 Provisioning 职责）
- **3 个 Provisioning 实例共享** `prompts/provisioning.md`，通过 `description` 注入专业方向，**不分别维护三份 prompt**
- **派发载荷 4 块结构**：任务头 + 原始用户目标 + 关键画像 + 方案段落，缺一不可
- **plan_store 归属 PlanningAgent**：方案持久化（场景 1/2 保存、场景 4 读取）统一由 Planning 管理，Orchestrator 不直接调用

## Skills 开发规范

遵循 Google ADK Agent Skills Design Patterns，详见 @.claude/rules/skills_rules.md。

本项目当前 Skills 范式分布：

- **Instructional**：`plan_design` / `insight_plan` / `insight_reflect`
- **Inversion**：`goal_parsing`
- **Reviewer**：`plan_review`
- **Tool Wrapper**：`cei_pipeline` / `cei_score_query` / `fault_diagnosis` / `remote_optimization` / `experience_assurance` / `plan_store` / `insight_decompose` / `insight_query` / `insight_nl2code`
- **Pipeline**：`wifi_simulation`
- **Generator**：`insight_report`

## Python 代码规范

- **类型注解**：所有函数必须有完整类型注解（参数 + 返回值），使用内置泛型（`list[str]`、`dict[str, Any]`）
- **Docstring**：公开函数和类必须有 docstring
- **私有符号**：模块内部函数/变量以 `_` 开头
- **常量**：模块级常量全大写，放在 import 之后、函数之前
- **异常处理**：core 层 try/except 包裹所有 DB 和 IO 操作，失败写日志不抛异常
- **格式化**：`ruff format .`；**Lint**：`ruff check --fix .`

## Git 提交规范

类型：`feat` | `fix` | `refactor` | `docs` | `skill`（SKILL.md/scripts/references）| `test` | `config`

- 禁止 `--force` 推送到 main/master
- 使用 `git push -u origin <branch>` 通过 PAT URL 直接推送
- 严禁使用 GitHub MCP Server 工具（mcp__github__push_files 等）提交或推送代码
- 新增/删除模块、架构或目录结构变更时必须同步更新 README.md

## 开发命令

```bash
uv sync                                   # 安装全部依赖（含 vendor editable 包）
uv run python ui/app.py                   # 启动 Gradio UI (localhost:7860)
uv run pytest tests/test_smoke.py -v      # 冒烟测试 (51 项)
ruff format . && ruff check --fix .       # 格式化 + Lint
```

## 禁止事项

- ❌ 不要在业务 Skill 里做业务规则判断（业务规则归属 PlanningAgent 的 LLM）
- ❌ 不要在 Provisioning 里跳过 `get_skill_instructions` 直接猜参数（Step 1 是强制的）
- ❌ 不要改写 Skill stdout（包括 YAML/JSON 配置、ECharts 数据、Markdown 报告）
- ❌ 不要让某个 SubAgent 调用子集之外的 Skill
- ❌ 不要在 Skill 脚本中感知 `session_id`，持久化由 core 层处理
- ❌ observability 写入失败必须静默，禁止抛异常阻断主流程
- ❌ 不要让 Orchestrator 推导 Skill 参数，参数提取是 Provisioning 的职责
- ❌ 不要让 PlanningAgent 自行派发 Provisioning，那是 Orchestrator 的职责
- ❌ plan_review 校验失败必须呈现给用户，禁止自动修正重试
