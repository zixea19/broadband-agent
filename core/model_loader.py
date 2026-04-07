"""从 configs/model.yaml 加载模型配置，返回 agno Model 实例。"""

import os
from pathlib import Path
from typing import Any, Dict

import yaml
from loguru import logger

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "model.yaml"


def load_model_config(config_path: Path = _CONFIG_PATH) -> Dict[str, Any]:
    """读取 model.yaml 并返回字典。"""
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    logger.info(f"模型配置加载成功: provider={cfg.get('provider')}, model={cfg.get('model')}")
    return cfg


def create_model(config: Dict[str, Any] = None):
    """根据配置创建 agno Model 实例。

    Returns:
        agno Model 实例 (OpenAIChat / OpenAILike / OpenRouter)
    """
    if config is None:
        config = load_model_config()

    provider = config.get("provider", "openai")
    # 优先使用 yaml 中直接配置的 api_key，其次从环境变量读取
    api_key = config.get("api_key", "") or ""
    if not api_key:
        api_key_env = config.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env, "")

    common_params = {
        "id": config.get("model", "gpt-4o-mini"),
        "api_key": api_key or None,
        "temperature": config.get("temperature", 0.3),
        "max_tokens": config.get("max_tokens", 4096),
        "timeout": config.get("timeout", 60),
    }

    # 自定义 role_map（用于不支持 developer 角色的 OpenAI 兼容 API）
    role_map = config.get("role_map")

    if provider == "openrouter":
        from agno.models.openrouter import OpenRouter
        params = {**common_params, "base_url": config.get("base_url", "https://openrouter.ai/api/v1")}
        if role_map:
            params["role_map"] = role_map
        model = OpenRouter(**params)
    elif provider == "openai":
        from agno.models.openai import OpenAIChat
        params = {**common_params}
        base_url = config.get("base_url")
        if base_url:
            params["base_url"] = base_url
        if role_map:
            params["role_map"] = role_map
        model = OpenAIChat(**params)
    elif provider == "openai_like":
        from agno.models.openai.like import OpenAILike
        model = OpenAILike(
            **common_params,
            base_url=config.get("base_url", ""),
        )
    else:
        # 通用 OpenAI 兼容
        from agno.models.openai.like import OpenAILike
        model = OpenAILike(
            **common_params,
            base_url=config.get("base_url", ""),
        )

    logger.info(f"模型创建成功: {provider} / {common_params['id']}")
    return model
