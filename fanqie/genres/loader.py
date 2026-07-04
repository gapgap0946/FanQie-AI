"""题材模板加载器."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Optional

from fanqie.models import GoldenThreeConfig

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class WorldModulesConfig:
    """世界观模块配置."""
    required: list[str] = field(default_factory=lambda: ["power_system", "geography", "history", "drive", "factions", "resources"])
    extra: list[str] = field(default_factory=list)


@dataclass
class ProtagonistConfig:
    """主角设定配置."""
    identity_hint: str = ""
    motivation_hint: str = ""
    arc_hint: str = ""


@dataclass
class CivilizationNormsConfig:
    """文明共识配置."""
    count: int = 5
    prompt_hint: str = ""


@dataclass
class GenreProfile:
    """题材模板配置."""
    id: str
    name: str
    description: str = ""
    chapter_types: list[str] = field(default_factory=list)
    fatigue_words: list[str] = field(default_factory=list)
    numerical_system: bool = False
    power_scaling: bool = False
    era_research: bool = False
    pacing_rule: str = ""
    satisfaction_types: list[str] = field(default_factory=list)
    rules: dict[str, str] = field(default_factory=dict)
    style_defaults: dict = field(default_factory=dict)
    prohibitions: list[str] = field(default_factory=list)
    audit_dimensions: list[int] = field(default_factory=list)
    source_path: str = ""
    # 新增 Foundation 相关字段
    world_modules: "WorldModulesConfig | None" = None
    world_emphasis: dict[str, str] = field(default_factory=dict)
    protagonist_config: "ProtagonistConfig | None" = None
    civilization_norms_config: "CivilizationNormsConfig | None" = None
    golden_three_config: "GoldenThreeConfig | None" = None

    @classmethod
    def from_toml(cls, path: str) -> "GenreProfile":
        with open(path, "rb") as f:
            data = tomllib.load(f)

        meta = data.get("meta", {})
        craft = data.get("craft", {})
        rules = craft.get("rules", {})
        style = craft.get("style_defaults", {})
        proh = data.get("prohibitions", {})
        audit = data.get("audit", {})

        # 解析新增字段
        wm_data = craft.get("world_modules", {})
        world_modules = WorldModulesConfig(
            required=wm_data.get("required", ["power_system", "geography", "history", "drive", "factions", "resources"]),
            extra=wm_data.get("extra", []),
        ) if wm_data else None

        world_emphasis = wm_data.get("emphasis", {}) if wm_data else {}

        p_data = craft.get("protagonist", {})
        protagonist_config = ProtagonistConfig(
            identity_hint=p_data.get("identity_hint", ""),
            motivation_hint=p_data.get("motivation_hint", ""),
            arc_hint=p_data.get("arc_hint", ""),
        ) if p_data else None

        cn_data = craft.get("civilization_norms", {})
        civilization_norms_config = CivilizationNormsConfig(
            count=cn_data.get("count", 5),
            prompt_hint=cn_data.get("prompt_hint", ""),
        ) if cn_data else None

        # 解析黄金三章配置
        gt_data = craft.get("golden_three", {})
        golden_three_config = GoldenThreeConfig(
            chapter_1_structure=gt_data.get("chapter_1_structure", ""),
            chapter_1_rules=gt_data.get("chapter_1_rules", []),
            chapter_2_structure=gt_data.get("chapter_2_structure", ""),
            chapter_2_rules=gt_data.get("chapter_2_rules", []),
            chapter_3_structure=gt_data.get("chapter_3_structure", ""),
            chapter_3_rules=gt_data.get("chapter_3_rules", []),
        ) if gt_data else None

        return cls(
            id=meta.get("id", ""),
            name=meta.get("name", ""),
            description=meta.get("description", ""),
            chapter_types=craft.get("chapter_types", []),
            fatigue_words=craft.get("fatigue_words", []),
            numerical_system=craft.get("numerical_system", False),
            power_scaling=craft.get("power_scaling", False),
            era_research=craft.get("era_research", False),
            pacing_rule=craft.get("pacing_rule", ""),
            satisfaction_types=craft.get("satisfaction_types", []),
            rules=rules if isinstance(rules, dict) else {},
            style_defaults=style if isinstance(style, dict) else {},
            prohibitions=proh.get("items", []),
            audit_dimensions=audit.get("dimensions", []),
            source_path=path,
            world_modules=world_modules,
            world_emphasis=world_emphasis,
            protagonist_config=protagonist_config,
            civilization_norms_config=civilization_norms_config,
            golden_three_config=golden_three_config,
        )


def get_genres_dir() -> str:
    """获取题材模板目录."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "genres")


def list_builtin_genres() -> list[str]:
    """列出内置题材 ID."""
    builtin = os.path.join(get_genres_dir(), "builtin")
    if not os.path.isdir(builtin):
        return []
    return [
        f[:-5] for f in os.listdir(builtin)
        if f.endswith(".toml")
    ]


def list_custom_genres() -> list[str]:
    """列出自定义题材 ID."""
    custom = os.path.join(get_genres_dir(), "custom")
    if not os.path.isdir(custom):
        return []
    return [
        f[:-5] for f in os.listdir(custom)
        if f.endswith(".toml")
    ]


def list_all_genres() -> dict[str, str]:
    """列出所有题材 {id: source}."""
    result = {}
    for gid in list_builtin_genres():
        result[gid] = "builtin"
    for gid in list_custom_genres():
        result[gid] = "custom"
    return result


def load_genre(genre_id: str) -> Optional[GenreProfile]:
    """加载指定题材."""
    genres_dir = get_genres_dir()
    for source in ("builtin", "custom"):
        path = os.path.join(genres_dir, source, f"{genre_id}.toml")
        if os.path.isfile(path):
            return GenreProfile.from_toml(path)
    return None


def get_genre_path(genre_id: str) -> Optional[str]:
    """获取题材文件路径."""
    genres_dir = get_genres_dir()
    for source in ("builtin", "custom"):
        path = os.path.join(genres_dir, source, f"{genre_id}.toml")
        if os.path.isfile(path):
            return path
    return None
