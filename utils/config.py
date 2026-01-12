from dataclasses import dataclass

from astrbot.api import AstrBotConfig


@dataclass(frozen=True)
class PluginConfig:
    """插件全局配置（严格直通 + 拍平）"""

    # ===== rendering =====
    timeout_analysis: float
    timeout_compile: float
    max_concurrent_tasks: int
    ppi: float
    giant_threshold: int
    split_height: int
    webp_limit: int

    # ===== other =====
    ignored_plugins: list[str]
    send_hint: bool

    @classmethod
    def load(cls, raw_cfg: AstrBotConfig) -> "PluginConfig":
        return cls(
            **raw_cfg["rendering"],
            ignored_plugins=raw_cfg["ignored_plugins"],
            send_hint=raw_cfg["send_hint"],
        )
