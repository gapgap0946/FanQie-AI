"""配置管理."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import yaml


DEFAULT_CONFIG = {
    "llm": {
        "provider": "custom",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "api_key_env": "FANQIE_API_KEY",
        "model": "gpt-4o",
        "temperature": 0.7,
        "max_tokens": 4096,
    },
    "writing": {
        "default_chapter_words": 2000,
        "target_chapters": 500,
        "review_retries": 1,
        "core_hooks_count": 5,
        "context_window_summaries": 4,
        "context_window_hooks": 6,
    },
    "paths": {
        "data_dir": "data",
    },
}


def _get_config_dir() -> Path:
    return Path.home() / ".fanqie"


def _get_config_path() -> Path:
    return _get_config_dir() / "config.yaml"


def _get_project_config_path() -> Path:
    return Path.cwd() / "fanqie.yaml"


def load_config() -> dict:
    """加载全局配置 + 项目配置."""
    config = DEFAULT_CONFIG.copy()

    # 全局配置
    global_path = _get_config_path()
    if global_path.exists():
        with open(global_path, "r", encoding="utf-8") as f:
            global_cfg = yaml.safe_load(f) or {}
            _deep_merge(config, global_cfg)

    # 项目配置
    project_path = _get_project_config_path()
    if project_path.exists():
        with open(project_path, "r", encoding="utf-8") as f:
            project_cfg = yaml.safe_load(f) or {}
            _deep_merge(config, project_cfg)

    # 环境变量覆盖 API key
    api_key_env = config.get("llm", {}).get("api_key_env", "FANQIE_API_KEY")
    env_key = os.environ.get(api_key_env)
    if env_key:
        config["llm"]["api_key"] = env_key

    return config


def save_global_config(config: dict) -> None:
    """保存全局配置."""
    _get_config_dir().mkdir(parents=True, exist_ok=True)
    with open(_get_config_path(), "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, default_flow_style=False)


def get_llm_config() -> dict:
    """获取 LLM 配置."""
    cfg = load_config()
    return cfg.get("llm", {})


def get_writing_config() -> dict:
    """获取写作配置."""
    cfg = load_config()
    return cfg.get("writing", {})


def _deep_merge(base: dict, override: dict) -> None:
    """深度合并配置."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
