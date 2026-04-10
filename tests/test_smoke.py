"""冒烟测试 — 覆盖新架构 (Team + 10 Skills) 的导入、配置与脚本执行。"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

# 确保项目根目录在 path
_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ============================================================================
# 配置 & 目录结构
# ============================================================================


def test_config_files_exist():
    """配置文件存在。"""
    root = Path(_ROOT)
    assert (root / "configs" / "model.yaml").exists()
    assert (root / "configs" / "agents.yaml").exists()
    assert (root / "configs" / "downstream.yaml").exists()


def test_model_config_loads():
    from core.model_loader import load_model_config
    cfg = load_model_config()
    assert "provider" in cfg
    assert "model" in cfg


def test_agents_config_structure():
    """agents.yaml 结构正确：team + 5 个 agents。"""
    import yaml
    cfg_path = Path(_ROOT) / "configs" / "agents.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    assert "team" in cfg
    assert cfg["team"]["mode"] == "coordinate"
    assert cfg["team"]["prompt"] == "prompts/orchestrator.md"

    agents = cfg.get("agents", {})
    expected_agents = {
        "planning",
        "insight",
        "provisioning_wifi",
        "provisioning_delivery",
        "provisioning_cei_chain",
    }
    assert expected_agents.issubset(agents.keys())

    # Planning 挂载 3 个 Skill
    assert set(agents["planning"]["skills"]) == {"goal_parsing", "plan_design", "plan_review"}
    # CEI 链实例挂载 3 个 Skill
    assert set(agents["provisioning_cei_chain"]["skills"]) == {
        "cei_pipeline",
        "fault_diagnosis",
        "remote_optimization",
    }
    # WIFI 实例只挂 wifi_simulation
    assert agents["provisioning_wifi"]["skills"] == ["wifi_simulation"]
    # Delivery 实例只挂 differentiated_delivery
    assert agents["provisioning_delivery"]["skills"] == ["differentiated_delivery"]


def test_all_skills_present():
    """10 个 Skill 目录均存在且含 SKILL.md。"""
    skills_dir = Path(_ROOT) / "skills"
    expected_skills = [
        "goal_parsing",
        "plan_design",
        "plan_review",
        "cei_pipeline",
        "fault_diagnosis",
        "remote_optimization",
        "differentiated_delivery",
        "wifi_simulation",
        "data_insight",
        "report_rendering",
    ]
    for name in expected_skills:
        skill_path = skills_dir / name
        assert skill_path.exists(), f"Skill 目录缺失: {name}"
        assert (skill_path / "SKILL.md").exists(), f"SKILL.md 缺失: {name}"


def test_all_prompts_present():
    """4 份 prompt 作业手册均存在且非空。"""
    prompts_dir = Path(_ROOT) / "prompts"
    for name in ("orchestrator.md", "planning.md", "insight.md", "provisioning.md"):
        p = prompts_dir / name
        assert p.exists(), f"Prompt 缺失: {name}"
        assert len(p.read_text(encoding="utf-8")) > 200, f"Prompt 太短: {name}"


def test_old_artifacts_removed():
    """旧架构的文件已清理（避免代码引用旧路径）。"""
    root = Path(_ROOT)
    assert not (root / "configs" / "agent.yaml").exists()
    assert not (root / "prompts" / "main_agent_system.md").exists()
    for old_skill in (
        "slot_filling",
        "solution_generation",
        "solution_verification",
        "cei_config",
        "fault_config",
        "remote_loop",
        "report_generation",
    ):
        assert not (root / "skills" / old_skill).exists(), f"旧 skill 未清理: {old_skill}"


# ============================================================================
# Skill 脚本执行（参数 schema 驱动）
# ============================================================================


def _load_script(skill_name: str, script_name: str):
    """从 skill 目录动态加载脚本模块，返回模块对象。"""
    path = Path(_ROOT) / "skills" / skill_name / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"{skill_name}_{script_name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_goal_parsing_slot_engine():
    mod = _load_script("goal_parsing", "slot_engine.py")
    result = json.loads(mod.process("", "{}"))
    assert "state" in result
    assert result["is_complete"] is False
    assert len(result["missing_slots"]) > 0

    result2 = json.loads(mod.process("直播套餐卖场走播用户，18:00-22:00 保障抖音直播", "{}"))
    state = result2["state"]
    assert state.get("package_type") == "直播套餐"
    assert state.get("scenario") == "卖场走播"
    assert "18:00-22:00" in (state.get("time_window") or "")
    assert state.get("guarantee_app") == "抖音"


def test_plan_review_checker():
    mod = _load_script("plan_review", "checker.py")
    result = json.loads(mod.review("## WIFI 仿真方案\n**启用**: true"))
    assert "passed" in result
    assert "violations" in result
    assert "recommendations" in result
    assert "checks" in result
    assert len(result["checks"]) == 4


def test_cei_pipeline_skill_schema():
    """SKILL.md 声明新的 weights Tool Wrapper schema，旧 Generator schema 已清理。"""
    skill_md = (
        Path(_ROOT) / "skills" / "cei_pipeline" / "SKILL.md"
    ).read_text(encoding="utf-8")
    # 新 schema 关键字
    for keyword in (
        "Tool Wrapper",
        "weights",
        "ServiceQualityWeight",
        "WiFiNetworkWeight",
        "StabilityWeight",
        "STAKPIWeight",
        "GatewayKPIWeight",
        "RateWeight",
        "ODNWeight",
        "OLTKPIWeight",
        "fae_poc",
        "cei_threshold_config.py",
    ):
        assert keyword in skill_md, f"SKILL.md 缺少关键字: {keyword}"
    # 旧 schema 关键字应已被清理
    for stale in (
        "render.py",
        "cei_spark",
        "granularity",
        "live_streaming",
        "time_window",
        "target_pon",
    ):
        assert stale not in skill_md, f"SKILL.md 残留旧 schema: {stale}"


def test_fault_diagnosis_render():
    mod = _load_script("fault_diagnosis", "render.py")
    result = json.loads(
        mod.render(
            json.dumps(
                {
                    "fault_tree_enabled": True,
                    "whitelist_rules": ["偶发卡顿"],
                    "severity_threshold": "warning",
                }
            )
        )
    )
    assert result["skill"] == "fault_diagnosis"
    assert result["params"]["fault_tree_enabled"] is True
    assert "偶发卡顿" in result["config_json"]
    assert "dispatch_result" in result


def test_remote_optimization_skill_schema():
    """SKILL.md 声明了新的 strategy / rectification_method / operation_time schema。"""
    skill_md = (
        Path(_ROOT) / "skills" / "remote_optimization" / "SKILL.md"
    ).read_text(encoding="utf-8")
    for keyword in (
        "strategy",
        "rectification_method",
        "operation_time",
        "immediate",
        "scheduled",
        "idle",
        "fae_poc",
    ):
        assert keyword in skill_md, f"SKILL.md 缺少关键字: {keyword}"
    # 旧 schema 关键字应已被清理
    for stale in ("trigger_mode", "coverage_weak_enabled"):
        assert stale not in skill_md, f"SKILL.md 残留旧 schema: {stale}"


def test_remote_optimization_normalize_params():
    """manual_batch_optimize 的参数归一化正确处理各种输入。"""
    mod = _load_script("remote_optimization", "manual_batch_optimize.py")

    # JSON list
    normalized = mod._normalize_params(
        {"strategy": "idle", "rectification_method": [1, 2]}
    )
    assert normalized["strategy"] == "idle"
    assert normalized["rectification_method"] == [1, 2]

    # 逗号分隔字符串
    normalized = mod._normalize_params(
        {"strategy": "scheduled", "rectification_method": "1,3,4", "operation_time": "0-0-3-*-*-*"}
    )
    assert normalized["rectification_method"] == [1, 3, 4]
    assert normalized["operation_time"] == "0-0-3-*-*-*"

    # 空值 → None（代表全部）
    normalized = mod._normalize_params({"strategy": "immediate"})
    assert normalized["rectification_method"] is None


def test_remote_optimization_invalid_params_rejected():
    """非法 strategy / rectification_method 应被拒绝。"""
    mod = _load_script("remote_optimization", "manual_batch_optimize.py")
    import pytest as _pytest

    with _pytest.raises(ValueError, match="strategy"):
        mod._normalize_params({"strategy": "bogus"})

    with _pytest.raises(ValueError, match="rectification_method"):
        mod._normalize_params({"strategy": "idle", "rectification_method": [5]})


def test_remote_optimization_cli_args_builder():
    """_build_cli_args 生成与 argparse 兼容的参数序列。"""
    mod = _load_script("remote_optimization", "manual_batch_optimize.py")

    cli = mod._build_cli_args(
        {
            "strategy": "scheduled",
            "rectification_method": [1, 2, 3],
            "operation_time": "0-0-0-*-*-*",
            "config": None,
        }
    )
    assert cli[:2] == ["--strategy", "scheduled"]
    assert "--rectification-method" in cli
    assert "1,2,3" in cli
    assert "--operation-time" in cli
    assert "0-0-0-*-*-*" in cli

    # strategy != scheduled 时不带 --operation-time
    cli = mod._build_cli_args(
        {
            "strategy": "idle",
            "rectification_method": None,
            "operation_time": "0-0-0-*-*-*",
            "config": None,
        }
    )
    assert "--operation-time" not in cli
    assert "--rectification-method" not in cli


def test_remote_optimization_execute_graceful_failure():
    """未部署 NCELogin.py / config.ini 时,execute() 返回结构化失败而非抛异常。"""
    mod = _load_script("remote_optimization", "manual_batch_optimize.py")
    result = mod.execute(
        {
            "strategy": "idle",
            "rectification_method": [1, 2],
            "operation_time": "0-0-0-*-*-*",
            "config": None,
        }
    )
    assert result["skill"] == "remote_optimization"
    assert "params" in result
    assert "dispatch_result" in result
    # 当前 CI 环境未部署 fae_poc/config.ini 或 fae_poc/NCELogin.py,
    # 应返回 status=failed + stage=deployment_check 或 ncelogin_import
    assert result["dispatch_result"]["status"] == "failed"
    assert result["dispatch_result"]["stage"] in {
        "deployment_check",
        "ncelogin_import",
    }


def test_remote_optimization_dual_syspath_injection():
    """脚本顶部 prelude 同时注入项目根 + fae_poc 目录到 sys.path。

    这保证 `from fae_poc import ...` 和 `from NCELogin import NCELogin`
    两种导入风格都能工作。
    """
    # 加载脚本 (触发其顶部的 sys.path 注入)
    _load_script("remote_optimization", "manual_batch_optimize.py")
    assert _ROOT in sys.path, "项目根未注入 sys.path"
    fae_poc_dir = str(Path(_ROOT) / "fae_poc")
    assert fae_poc_dir in sys.path, "fae_poc/ 目录未注入 sys.path"


def test_remote_optimization_bare_ncelogin_import_works():
    """验证 bare 导入 `from NCELogin import NCELogin` 的路径在 CI 环境也可工作。

    做法: 临时在 fae_poc/ 下放一个 stub NCELogin.py,触发导入,然后清理。
    测试结束后不能残留 stub,也不能污染 sys.modules。
    """
    _load_script("remote_optimization", "manual_batch_optimize.py")

    fae_poc_dir = Path(_ROOT) / "fae_poc"
    stub_path = fae_poc_dir / "NCELogin.py"
    stub_existed = stub_path.exists()
    backup = stub_path.read_text(encoding="utf-8") if stub_existed else None

    try:
        if not stub_existed:
            stub_path.write_text(
                "class NCELogin:\n"
                "    def __init__(self, config_file=None):\n"
                "        self.config_file = config_file\n",
                encoding="utf-8",
            )
        # 确保缓存被清理后重新导入
        sys.modules.pop("NCELogin", None)
        import NCELogin as _bare  # type: ignore  # noqa: F401
        assert hasattr(_bare, "NCELogin")
        instance = _bare.NCELogin(config_file="/tmp/fake.ini")
        assert instance.config_file == "/tmp/fake.ini"
    finally:
        sys.modules.pop("NCELogin", None)
        if not stub_existed and stub_path.exists():
            stub_path.unlink()
        elif stub_existed and backup is not None:
            stub_path.write_text(backup, encoding="utf-8")


def test_fae_poc_package_importable():
    """fae_poc 包可 import,即使 NCELogin.py / config.ini 未部署。"""
    import importlib
    # 确保项目根在 sys.path
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    fae_poc = importlib.import_module("fae_poc")
    assert hasattr(fae_poc, "DEFAULT_CONFIG_PATH")
    assert hasattr(fae_poc, "EXAMPLE_CONFIG_PATH")
    assert hasattr(fae_poc, "require_config")
    assert hasattr(fae_poc, "require_ncelogin")
    # 未部署时 require_* 应抛出带引导信息的错误
    import pytest as _pytest
    with _pytest.raises(FileNotFoundError, match="config.ini"):
        fae_poc.require_config()
    # NCELogin.py 未提交时应优雅提示
    if fae_poc.NCELogin is None:
        with _pytest.raises(RuntimeError, match="NCELogin"):
            fae_poc.require_ncelogin()


def test_fae_poc_example_committed():
    """config.ini.example 模板必须提交,真实 config.ini 不得提交。"""
    fae_poc_dir = Path(_ROOT) / "fae_poc"
    assert (fae_poc_dir / "__init__.py").exists()
    assert (fae_poc_dir / "config.ini.example").exists()
    # 真实文件不应出现在 git 跟踪的检查点 — 本测试不强行断言其不存在
    # （开发者可能已在本地部署），仅确保 .gitignore 规则存在
    gitignore = (Path(_ROOT) / ".gitignore").read_text(encoding="utf-8")
    assert "fae_poc/config.ini" in gitignore
    assert "fae_poc/NCELogin.py" in gitignore


def test_differentiated_delivery_render():
    mod = _load_script("differentiated_delivery", "render.py")
    result = json.loads(
        mod.render(
            json.dumps(
                {
                    "slice_type": "application_slice",
                    "target_app": "抖音",
                    "whitelist": ["douyin.com"],
                    "bandwidth_guarantee_mbps": 50,
                }
            )
        )
    )
    assert result["skill"] == "differentiated_delivery"
    assert result["params"]["target_app"] == "抖音"
    assert "抖音" in result["config_json"]
    assert "slice_id" in result["dispatch_result"]


def test_data_insight_query_stage():
    mod = _load_script("data_insight", "mock_query.py")
    result = json.loads(mod.query("query"))
    assert result["skill"] == "data_insight"
    assert result["stage"] == "query"
    assert "data" in result
    assert "echarts_option" in result
    assert result["echarts_option"]["series"][0]["type"] == "bar"
    assert "summary" in result
    assert "priority_pons" in result["summary"]


def test_data_insight_attribution_stage():
    mod = _load_script("data_insight", "mock_query.py")
    result = json.loads(mod.query("attribution"))
    assert result["stage"] == "attribution"
    assert "analysis" in result
    assert result["echarts_option"]["series"][0]["type"] == "radar"


def test_wifi_simulation_four_steps():
    mod = _load_script("wifi_simulation", "simulate.py")
    result = json.loads(mod.simulate("{}"))
    assert result["skill"] == "wifi_simulation"
    assert len(result["steps"]) == 4
    step_names = [s["name"] for s in result["steps"]]
    assert step_names == [
        "户型图识别",
        "热力图生成",
        "RSSI 采集",
        "选点对比",
    ]
    for step in result["steps"]:
        assert "echarts_option" in step
        assert step["status"] == "success"


def test_report_rendering():
    mod = _load_script("report_rendering", "render_report.py")
    ctx = json.dumps(
        {
            "title": "测试报告",
            "summary": {
                "priority_pons": ["PON-2/0/5"],
                "distinct_issues": ["带宽利用率过高"],
                "scope_indicator": "regional",
            },
            "analysis": [
                {
                    "pon_port": "PON-2/0/5",
                    "cei_score": 48.9,
                    "issues": ["带宽利用率过高"],
                    "probable_causes": ["用户数过多"],
                    "recommendation": "建议优先关注",
                }
            ],
        }
    )
    md = mod.render(ctx)
    assert "测试报告" in md
    assert "PON-2/0/5" in md
    assert "带宽利用率过高" in md


# ============================================================================
# UI 流式处理 (ui/app.py chat_handler)
# ============================================================================


class _FakeEvent:
    """模拟 agno 事件对象。只实现 chat_handler 会访问的字段。"""

    def __init__(
        self,
        event: str,
        agent_id: str = "",
        agent_name: str = "",
        team_id: str = "",
        team_name: str = "",
        reasoning_content: str = "",
        content=None,
        tool=None,
    ):
        self.event = event
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.team_id = team_id
        self.team_name = team_name
        self.reasoning_content = reasoning_content
        self.content = content
        self.tool = tool


class _FakeTool:
    def __init__(self, tool_name: str, tool_args=None, result=None):
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.result = result


class _FakeTracer:
    """无副作用的 tracer 桩,吞掉所有 trace 调用。"""

    def __getattr__(self, _name):
        def _noop(*args, **kwargs):
            return None
        return _noop


class _FakeTeam:
    """模拟 agno Team, arun 返回一个手工构造的 async generator。"""

    def __init__(self, name: str, events):
        self.name = name
        self._events = events

    def arun(self, *args, **kwargs):
        events = self._events

        async def _gen():
            for ev in events:
                yield ev

        return _gen()


class _FakeCtx:
    def __init__(self, team):
        self.team = team
        self.tracer = _FakeTracer()
        self.db_session_id = None


def _run_chat_handler_sync(events, team_name: str = "home-broadband-team"):
    """同步运行 chat_handler,返回最终 history。

    用 asyncio.run 包住 async generator 的 drain。
    """
    import asyncio

    # 延迟导入避免测试模块顶层加载 gradio 等重依赖
    from ui import app as app_module

    fake_team = _FakeTeam(team_name, events)
    fake_ctx = _FakeCtx(fake_team)

    # monkey-patch session_manager + db
    orig_session_manager = app_module.session_manager

    class _FakeSessionManager:
        def get_or_create(self, _hash):
            return fake_ctx

    app_module.session_manager = _FakeSessionManager()
    try:
        async def _drain():
            last = []
            async for h in app_module.chat_handler(
                "test message",
                [],
                {"session_hash": "test-hash"},
            ):
                last = h
            return last

        return asyncio.run(_drain())
    finally:
        app_module.session_manager = orig_session_manager


def test_extract_source_id_member_event():
    from ui.app import _extract_source_id

    ev = _FakeEvent(event="ReasoningContentDelta", agent_id="provisioning_wifi")
    assert _extract_source_id(ev, is_leader=False) == "provisioning_wifi"

    # 空 agent_id 回退到 agent_name
    ev2 = _FakeEvent(event="ReasoningContentDelta", agent_id="", agent_name="provisioning_delivery")
    assert _extract_source_id(ev2, is_leader=False) == "provisioning_delivery"

    # 两者都为空
    ev3 = _FakeEvent(event="ReasoningContentDelta")
    assert _extract_source_id(ev3, is_leader=False) is None


def test_extract_source_id_leader_event():
    from ui.app import _extract_source_id

    ev = _FakeEvent(event="TeamReasoningContentDelta", team_id="home-broadband-team")
    assert _extract_source_id(ev, is_leader=True) == "home-broadband-team"

    ev2 = _FakeEvent(event="TeamReasoningContentDelta", team_id="", team_name="fallback-team")
    assert _extract_source_id(ev2, is_leader=True) == "fallback-team"


def test_is_team_leader_event():
    from ui.app import _is_team_leader_event

    assert _is_team_leader_event("TeamReasoningContentDelta") is True
    assert _is_team_leader_event("TeamRunContent") is True
    assert _is_team_leader_event("ReasoningContentDelta") is False
    assert _is_team_leader_event("RunContent") is False
    assert _is_team_leader_event("") is False


def test_chat_handler_per_source_reasoning_isolation():
    """核心回归测试:并行 member 的交错 ReasoningContentDelta 不得混词。

    模拟场景: wifi 和 delivery 两个 member 的推理 delta 在同一个流里交错。
    期望: 最终 history 里有两个独立的 thinking 块,每个只含单一 source 的
    内容;"透传产出" 这个被测试场景里的关键词必须完整出现在某一个块里,
    绝不能被切成 "6. 透" 和 "传产出" 分散到两个块中 (旧 bug 的症状)。
    """
    events = [
        # wifi 开始推理 (一段话)
        _FakeEvent(
            event="ReasoningContentDelta",
            agent_id="provisioning_wifi",
            agent_name="provisioning_wifi",
            reasoning_content="处理缺失项\n4. 展示推导过程\n5. 调用 Skill\n6. 透",
        ),
        # delivery 插入一段自己的推理 (bug 场景: 此刻会污染单 buffer)
        _FakeEvent(
            event="ReasoningContentDelta",
            agent_id="provisioning_delivery",
            agent_name="provisioning_delivery",
            reasoning_content="当前挂载的技能是 differentiated_delivery,有一个脚本 render.py。",
        ),
        # wifi 继续,补完被 delivery 打断的话
        _FakeEvent(
            event="ReasoningContentDelta",
            agent_id="provisioning_wifi",
            agent_name="provisioning_wifi",
            reasoning_content="传产出。",
        ),
        # wifi 的 reasoning 结束
        _FakeEvent(
            event="ReasoningCompleted",
            agent_id="provisioning_wifi",
            agent_name="provisioning_wifi",
        ),
        # delivery 也结束
        _FakeEvent(
            event="ReasoningCompleted",
            agent_id="provisioning_delivery",
            agent_name="provisioning_delivery",
        ),
    ]

    history = _run_chat_handler_sync(events)

    # 提取所有 thinking 块
    thinking_blocks = [
        m for m in history
        if isinstance(m, dict)
        and m.get("metadata", {}).get("title", "").startswith("💭")
    ]
    assert len(thinking_blocks) >= 2, f"应至少 2 个思考块(wifi + delivery),实际 {len(thinking_blocks)}"

    # 把每个块归属到 source (通过标题里的 display 名判断)
    wifi_content = ""
    delivery_content = ""
    for block in thinking_blocks:
        title = block["metadata"]["title"]
        content = block["content"]
        if "WIFI 仿真" in title:
            wifi_content += content
        elif "差异化承载" in title:
            delivery_content += content

    # 关键断言 1: wifi 的内容含完整的 "透传产出",没被切断
    assert "透传产出" in wifi_content, (
        f"wifi 的思考应含完整的'透传产出',实际: {wifi_content!r}"
    )
    # 关键断言 2: delivery 的内容含完整的 "differentiated_delivery"
    assert "differentiated_delivery" in delivery_content, (
        f"delivery 的思考应含 'differentiated_delivery',实际: {delivery_content!r}"
    )
    # 关键断言 3: wifi 的块里不能混进 delivery 的内容
    assert "differentiated_delivery" not in wifi_content, (
        f"wifi 思考块污染了 delivery 的内容: {wifi_content!r}"
    )
    # 关键断言 4: delivery 的块里不能混进 wifi 特有的内容
    assert "处理缺失项" not in delivery_content, (
        f"delivery 思考块污染了 wifi 的内容: {delivery_content!r}"
    )


def test_chat_handler_tool_call_from_other_member_does_not_contaminate():
    """member A 的 tool_call 可以让 member B 的思考分段,但绝不能把 A 的内容混到 B 的块里。

    说明: wifi 的首个事件就是 tool_call 时,徽章渲染会固化 delivery 的当前 buffer
    (设计意图: 不让徽章插在旧思考中间)。分段是可接受的,核心要求是每段内容只来
    自单一 source,不出现跨 member 的混词 (这才是原 bug 的症状)。
    """
    events = [
        # delivery 开始推理
        _FakeEvent(
            event="ReasoningContentDelta",
            agent_id="provisioning_delivery",
            agent_name="provisioning_delivery",
            reasoning_content="分析参数 schema",
        ),
        # wifi 首次出现 + 立即发起 tool_call (首次触发徽章 → 固化 delivery 当前 buffer)
        _FakeEvent(
            event="ToolCallStarted",
            agent_id="provisioning_wifi",
            agent_name="provisioning_wifi",
            tool=_FakeTool(tool_name="get_skill_instructions", tool_args={"skill_name": "wifi_simulation"}),
        ),
        # delivery 继续推理 (新 buffer,独立分段)
        _FakeEvent(
            event="ReasoningContentDelta",
            agent_id="provisioning_delivery",
            agent_name="provisioning_delivery",
            reasoning_content="确认字段对齐。",
        ),
        # delivery reasoning 结束
        _FakeEvent(
            event="ReasoningCompleted",
            agent_id="provisioning_delivery",
            agent_name="provisioning_delivery",
        ),
    ]

    history = _run_chat_handler_sync(events)

    delivery_blocks = [
        m for m in history
        if isinstance(m, dict)
        and "差异化承载" in m.get("metadata", {}).get("title", "")
        and m["metadata"]["title"].startswith("💭")
    ]
    assert len(delivery_blocks) >= 1, "delivery 思考块必须存在"

    # 核心断言 1: 每个 delivery 块的内容必须只来自 delivery,不含 wifi 的工具/思考痕迹
    for block in delivery_blocks:
        content = block["content"]
        assert "wifi_simulation" not in content, f"delivery 块被 wifi tool_call 污染: {content!r}"
        assert "get_skill_instructions" not in content, f"delivery 块被 wifi tool_call 污染: {content!r}"

    # 核心断言 2: delivery 的两段内容(可能分散在多个块里)都应被保留,没有丢失
    combined = "".join(b["content"] for b in delivery_blocks)
    assert "分析参数 schema" in combined, f"delivery 第一段内容丢失: {combined!r}"
    assert "确认字段对齐" in combined, f"delivery 第二段内容丢失: {combined!r}"

    # 顺序验证: 先出现的内容在前面的块里
    first_block_text = delivery_blocks[0]["content"]
    assert "分析参数 schema" in first_block_text, (
        f"delivery 第一段应出现在第一个块里,实际首块: {first_block_text!r}"
    )


def test_chat_handler_member_badge_once_per_member():
    """每个 member 一轮只渲染一次徽章,即使事件反复交错。"""
    events = [
        _FakeEvent(event="ReasoningContentDelta", agent_id="provisioning_wifi", reasoning_content="a"),
        _FakeEvent(event="ReasoningContentDelta", agent_id="provisioning_delivery", reasoning_content="b"),
        _FakeEvent(event="ReasoningContentDelta", agent_id="provisioning_wifi", reasoning_content="c"),
        _FakeEvent(event="ReasoningContentDelta", agent_id="provisioning_delivery", reasoning_content="d"),
        _FakeEvent(event="ReasoningCompleted", agent_id="provisioning_wifi"),
        _FakeEvent(event="ReasoningCompleted", agent_id="provisioning_delivery"),
    ]
    history = _run_chat_handler_sync(events)

    badges = [
        m for m in history
        if isinstance(m, dict) and m.get("metadata", {}).get("title", "").startswith("👤")
    ]
    # 每个 member 只应出现一个徽章
    wifi_badges = [b for b in badges if "WIFI 仿真" in b["metadata"]["title"]]
    delivery_badges = [b for b in badges if "差异化承载" in b["metadata"]["title"]]
    assert len(wifi_badges) == 1, f"wifi 徽章应 1 个,实际 {len(wifi_badges)}"
    assert len(delivery_badges) == 1, f"delivery 徽章应 1 个,实际 {len(delivery_badges)}"


# ============================================================================
# Agno Team 装配
# ============================================================================


def test_render_tool_call_started_returns_single_folded_block():
    """ToolCallStarted 阶段只有 inputs → 单条折叠块。"""
    from ui.chat_renderer import render_tool_call

    msgs = render_tool_call(
        "cei_pipeline",
        inputs={"weights": "ServiceQualityWeight:40"},
        member="provisioning_cei_chain",
    )
    assert isinstance(msgs, list)
    assert len(msgs) == 1
    assert msgs[0]["metadata"]["title"].startswith("🔧")
    assert "体验保障链" in msgs[0]["metadata"]["title"]
    assert "ServiceQualityWeight" in msgs[0]["content"]


def test_render_tool_call_completed_splits_stdout_into_expanded_block():
    """ToolCallCompleted 含 stdout → 折叠元数据块 + 展开产物块。"""
    from ui.chat_renderer import render_tool_call

    outputs = {
        "script_path": "scripts/cei_threshold_config.py",
        "returncode": 0,
        "stdout": '{"status": "success", "config_id": "CEI-12345"}',
        "stderr": "",
    }
    msgs = render_tool_call("cei_pipeline", outputs=outputs)
    assert len(msgs) == 2
    # 折叠块 (审计元数据)
    assert msgs[0]["metadata"]["title"].startswith("🔧")
    assert "returncode=0" in msgs[0]["content"]
    assert "✅" in msgs[0]["content"]
    # 展开块 (产物正文,无 metadata.title → Gradio 默认展开)
    assert "metadata" not in msgs[1]
    assert "cei_pipeline 产出" in msgs[1]["content"]
    assert "CEI-12345" in msgs[1]["content"]
    assert "```json" in msgs[1]["content"]


def test_render_tool_call_completed_markdown_stdout_inlined_raw():
    """stdout 以 '#' 开头的 Markdown 报告 → 展开块不加代码块包裹。"""
    from ui.chat_renderer import render_tool_call

    outputs = {
        "script_path": "scripts/render_report.py",
        "returncode": 0,
        "stdout": "# 网络质量洞察报告\n\n## PON-2/0/5\n- 带宽利用率过高",
        "stderr": "",
    }
    msgs = render_tool_call("report_rendering", outputs=outputs)
    assert len(msgs) == 2
    assert "```" not in msgs[1]["content"].split("report_rendering 产出")[1][:20]
    assert "# 网络质量洞察报告" in msgs[1]["content"]


def test_render_tool_call_completed_failure_no_stdout_single_block():
    """脚本失败且无 stdout → 只有折叠块,无展开块。"""
    from ui.chat_renderer import render_tool_call

    outputs = {
        "script_path": "scripts/cei_threshold_config.py",
        "returncode": 1,
        "stdout": "",
        "stderr": "FAE connection refused",
    }
    msgs = render_tool_call("cei_pipeline", outputs=outputs)
    assert len(msgs) == 1
    assert "❌" in msgs[0]["content"]
    assert "FAE connection refused" in msgs[0]["content"]


def test_render_tool_call_completed_parses_json_string_output():
    """回归: agno 可能把 Skill 脚本返回值序列化为 JSON 字符串后再放入
    ToolCallCompleted.tool.result。此时仍应走 Skill 格式路径拆分,不能退化为
    '返回结果: { 全量 dict }' 的兜底展示。"""
    import json as _json
    from ui.chat_renderer import render_tool_call

    outputs_str = _json.dumps(
        {
            "skill_name": "cei_pipeline",
            "script_path": "cei_threshold_config.py",
            "stdout": "CEI 权重配置下发成功 config_id=CEI-12345",
            "stderr": "InsecureRequestWarning: ...",
            "returncode": 0,
        }
    )
    msgs = render_tool_call("cei_pipeline", outputs=outputs_str)
    # 拆分为折叠审计块 + 展开产物块两条
    assert len(msgs) == 2
    # 折叠块含 script_path + returncode + stderr,**不是** 整个 dict 的 '返回结果' 兜底
    assert "cei_threshold_config.py" in msgs[0]["content"]
    assert "returncode=0" in msgs[0]["content"]
    assert "**返回结果**" not in msgs[0]["content"]
    assert "InsecureRequestWarning" in msgs[0]["content"]  # stderr 正确抽取
    # 展开块只含 stdout 正文
    assert "metadata" not in msgs[1]
    assert "config_id=CEI-12345" in msgs[1]["content"]


def test_render_tool_call_completed_with_both_inputs_and_outputs():
    """app.py 的 ToolCallCompleted 分支会同时传 inputs + outputs,让持久化块
    含入参解释 + 执行状态 + 展开产物。"""
    from ui.chat_renderer import render_tool_call

    msgs = render_tool_call(
        "cei_pipeline",
        inputs={"weights": "ServiceQualityWeight:40"},
        outputs={
            "script_path": "cei_threshold_config.py",
            "stdout": "ok",
            "stderr": "",
            "returncode": 0,
        },
    )
    assert len(msgs) == 2
    # 折叠审计块里应同时有 **输入参数** + 执行状态
    assert "**输入参数**" in msgs[0]["content"]
    assert "ServiceQualityWeight:40" in msgs[0]["content"]
    assert "✅" in msgs[0]["content"]
    assert "returncode=0" in msgs[0]["content"]
    # 展开块是 stdout 正文
    assert "metadata" not in msgs[1]
    assert "ok" in msgs[1]["content"]


def test_render_tool_call_completed_non_skill_output_single_block():
    """非 Skill 脚本返回 (无 stdout 键) → 单条折叠块包裹 JSON。"""
    from ui.chat_renderer import render_tool_call

    outputs = {"status": "ok", "data": [1, 2, 3]}
    msgs = render_tool_call("some_internal_tool", outputs=outputs)
    assert len(msgs) == 1
    assert "**返回结果**" in msgs[0]["content"]


def test_localskills_loads_all():
    """LocalSkills 能扫描并加载 10 个 Skill。"""
    from agno.skills.loaders.local import LocalSkills
    loader = LocalSkills(str(Path(_ROOT) / "skills"), validate=False)
    skills = loader.load()
    assert len(skills) == 10
    names = {s.name for s in skills}
    assert "goal_parsing" in names
    assert "plan_design" in names
    assert "cei_pipeline" in names
    assert "differentiated_delivery" in names


def test_create_team_structure():
    """create_team() 产出 1 leader + 5 member 的 Team。"""
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

    from agno.team import Team
    from agno.team.team import TeamMode
    from core.agent_factory import create_team

    team = create_team(session_id="smoke-test-session")
    assert isinstance(team, Team)
    assert team.mode == TeamMode.coordinate
    assert len(team.members) == 5

    member_names = [m.name for m in team.members]
    assert set(member_names) == {
        "planning",
        "insight",
        "provisioning_wifi",
        "provisioning_delivery",
        "provisioning_cei_chain",
    }

    # 每个 member 的 skills 子集正确
    for m in team.members:
        skill_names = {s.name for s in m.skills.get_all_skills()} if m.skills else set()
        if m.name == "planning":
            assert skill_names == {"goal_parsing", "plan_design", "plan_review"}
        elif m.name == "insight":
            assert skill_names == {"data_insight", "report_rendering"}
        elif m.name == "provisioning_wifi":
            assert skill_names == {"wifi_simulation"}
        elif m.name == "provisioning_delivery":
            assert skill_names == {"differentiated_delivery"}
        elif m.name == "provisioning_cei_chain":
            assert skill_names == {"cei_pipeline", "fault_diagnosis", "remote_optimization"}


# ============================================================================
# 可观测性
# ============================================================================


def test_db_init():
    from core.observability.db import Database
    import tempfile
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        d = Database(db_path)
        sid = d.create_session("test-hash")
        assert sid is not None
        assert d.get_session_id("test-hash") == sid
        d.insert_message(sid, "user", "hello")
        d.insert_trace(sid, "test-hash", "request", {"input": "hello"})
        d.end_session("test-hash", "test")
    finally:
        db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
