"""从 YAML 配置构造 agno.Agent 实例。"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from loguru import logger

from agno.agent import Agent
from agno.db.sqlite.sqlite import SqliteDb
from agno.skills import Skills
from agno.skills.loaders.local import LocalSkills

from core.model_loader import create_model, load_model_config

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_AGENT_CONFIG_PATH = _PROJECT_ROOT / "configs" / "agent.yaml"


def _load_agent_config(config_path: Path = _AGENT_CONFIG_PATH) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    logger.info(f"Agent 配置加载成功: name={cfg.get('name')}")
    return cfg


def _load_system_prompt(relative_path: str) -> str:
    prompt_path = _PROJECT_ROOT / relative_path
    if prompt_path.exists():
        content = prompt_path.read_text(encoding="utf-8")
        logger.debug(f"System prompt 加载: {prompt_path} ({len(content)} chars)")
        return content
    logger.warning(f"System prompt 文件不存在: {prompt_path}")
    return ""


def _load_skills(skills_dir: str) -> Optional[Skills]:
    """加载 skills 目录下的所有 Skill。"""
    skills_path = _PROJECT_ROOT / skills_dir
    if not skills_path.exists():
        logger.warning(f"Skills 目录不存在: {skills_path}")
        return None
    try:
        loader = LocalSkills(str(skills_path), validate=False)
        skills = Skills(loaders=[loader])
        names = skills.get_skill_names()
        logger.info(f"Skills 加载成功: {names}")
        return skills
    except Exception:
        logger.exception("Skills 加载失败")
        return None


def create_agent(session_id: str = None) -> Agent:
    """从配置文件创建 agno Agent 实例。

    Args:
        session_id: 会话标识符，用于隔离 memory

    Returns:
        配置好的 agno.Agent 实例
    """
    agent_cfg = _load_agent_config()
    model = create_model()

    # System prompt
    system_prompt = _load_system_prompt(agent_cfg.get("system_prompt_path", "prompts/main_agent_system.md"))

    # Skills
    skills = _load_skills(agent_cfg.get("skills_dir", "skills/"))

    # 将 Skills 元数据追加到 system_prompt，确保 LLM 能感知所有可用 Skill
    # 原因：Agent 以 system_message= 显式传入时，agno 早期 return（第 152 行），
    # 跳过内部的 skills.get_system_prompt_snippet() 注入（第 282-285 行），需手动补注。
    if skills is not None and system_prompt:
        try:
            skills_snippet = skills.get_system_prompt_snippet()
            if skills_snippet:
                system_prompt = system_prompt + "\n\n" + skills_snippet
                logger.debug(f"Skills snippet 已追加到 system_prompt ({len(skills_snippet)} chars)")
        except Exception:
            logger.warning("Skills snippet 获取失败，system prompt 将不含 Skills 描述")

    # SQLite 存储（用于 add_history_to_context）
    db_path = _PROJECT_ROOT / "data" / "agent_sessions.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = SqliteDb(db_file=str(db_path))

    # 构造 Agent
    agent = Agent(
        name=agent_cfg.get("name", "home-broadband-agent"),
        model=model,
        system_message=system_prompt if system_prompt else None,
        skills=skills,
        session_id=session_id,
        db=db,
        add_history_to_context=True,
        num_history_runs=agent_cfg.get("memory", {}).get("max_turns", 30),
        markdown=True,
        stream=True,
    )

    logger.info(f"Agent 创建成功: name={agent.name}, session_id={session_id}")
    return agent
