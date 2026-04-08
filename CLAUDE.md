# CLAUDE.md

## 项目概述

家宽网络调优智能助手。基于 Agno 框架的单体 Agent，通过 9 个 Skills 覆盖从意图识别到配置下发的完整流程。

核心模式：**单 Agent + Skills 路由 → 三类任务分流 → 模板渲染 → Mock 下游**

## 技术栈

Python 3.11+、Agno ≥ 2.5.14、Gradio 4.x（Web UI）、SQLite（会话持久化）、Jinja2（模板渲染）、loguru（日志）

## 项目结构

```
├── configs/
│   ├── model.yaml          # 模型配置（provider / base_url / api_key / role_map）
│   ├── agent.yaml          # Agent 名称 + 启用的 Skills 列表 + memory 配置
│   ├── downstream.yaml     # 下游接口（mock/real 切换）
├── core/
│   ├── agent_factory.py    # 从 YAML 构造 Agent（model + skills + prompt + sqlite）
│   ├── model_loader.py     # 模型实例化 + prompt tracer 注入
│   ├── session_manager.py  # session_hash → Agent + Tracer 隔离
│   ├── downstream_client.py # 下游 mock/real 双模式客户端
│   └── observability/      # SQLite DAO + loguru sink + JSONL tracer
├── skills/                 # 9 个自包含 Skills（每个含 SKILL.md）
│   ├── slot_filling/       # 槽位填充引擎（决策树追问）
│   ├── solution_generation/# 四类配置模板渲染（Jinja2）
│   ├── solution_verification/ # 约束校验（mock）
│   ├── cei_config/         # CEI Spark 配置
│   ├── wifi_simulation/    # Wifi 仿真配置
│   ├── fault_config/       # 故障检测配置
│   ├── remote_loop/        # 远程闭环配置
│   ├── data_insight/       # 数据查询 + 归因分析（mock）
│   └── report_generation/  # Markdown 报告渲染
├── prompts/main_agent_system.md  # System Prompt（任务识别 + 流程状态机）
├── ui/
│   ├── app.py              # Gradio 入口（异步流式输出）
│   └── chat_renderer.py    # 思考/工具调用/回答的折叠渲染
└── tests/test_smoke.py     # 冒烟测试
```

## 三类任务流程

```
综合目标: slot_filling → solution_generation → [solution_verification] → [report_generation]
具体功能: cei_config | wifi_simulation | fault_config | remote_loop → 展示 → 确认
数据洞察: data_insight → [report_generation]
```

## 架构要点

1. **Skills 自包含**：模板、脚本、参考配置全在 Skill 目录内，通过 `LocalSkills` 自动扫描
2. **会话隔离**：`SessionManager` 为每个 Gradio session_hash 创建独立 Agent + Tracer
3. **模板驱动**：`solution_generation` 使用 Jinja2 按用户画像渲染四类配置，禁止凭空编造参数
4. **可观测性双写**：SQLite（结构化查询）+ JSONL（日志归档），写入失败不影响主流程
5. **下游 mock/real 切换**：`downstream.yaml` 的 `mode` 字段控制，mock 模式随机返回预设响应
6. **prompt tracer**：monkey-patch `ainvoke_stream` 记录完整 LLM 输入，不侵入 Agno 内部

## Python 代码规范

- **类型注解**：所有函数必须有完整类型注解（参数 + 返回值），使用内置泛型（`list[str]`、`Dict[str, Any]`）
- **Docstring**：公开函数和类必须有 docstring，私有函数视复杂度决定
- **私有符号**：模块内部函数/变量以 `_` 开头（如 `_MOCK_DATA`、`_load_config`）
- **常量**：模块级常量全大写，放在 import 之后、函数之前
- **异常处理**：core 层 try/except 包裹所有 DB 和 IO 操作，失败写日志不抛异常
- **格式化**：`ruff format .`；**Lint**：`ruff check --fix .`

## Git 提交规范

类型：`feat` | `fix` | `refactor` | `docs` | `skill`（SKILL.md/scripts/references）| `test` | `config`

- 禁止 `--force` 推送到 main/master
- 使用 git push -u origin <branch> 通过 PAT URL 直接推送
- 严禁使用 GitHub MCP Server 工具（mcp__github__push_files 等）提交或推送代码，速度极慢且不可靠
- 新增/删除模块、架构或目录结构变更时必须同步更新 README.md

## 开发命令

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your-key"
python ui/app.py                          # 启动 Gradio UI (localhost:7860)
pytest tests/test_smoke.py -v             # 冒烟测试
```

## 配置说明

- `model.yaml`：支持 openai / openai_like / openrouter，`role_map` 适配非标准 API
- `slot_schema.yaml`：定义槽位依赖树，`branches` 实现条件分支选项
- `agent.yaml`：`enabled_skills` 控制加载哪些 Skill，`memory.max_turns` 控制上下文长度

## 禁止事项

- 不要绕过 Skill 模板直接编造配置参数
- 不要在 Skill 脚本中感知 session_id，持久化由 core 层处理
- 不要跳过 `get_skill_instructions` 直接猜测脚本文件名
- observability 写入失败必须静默，禁止抛异常阻断主流程
