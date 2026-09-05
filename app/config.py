"""config.yaml 加载：缺失文件/缺失键回退默认值，类型错误抛 ConfigError。"""
from __future__ import annotations

import os
from dataclasses import dataclass

import yaml


class ConfigError(Exception):
    """配置文件无法解析或字段类型非法。"""


@dataclass
class Config:
    hotkey: str = "ctrl+shift+space"
    auto_paste: bool = True
    restore_clipboard: bool = True
    restore_delay_sec: float = 1.5
    beep: bool = True
    min_duration_ms: int = 300
    sample_rate: int = 16000


_FIELD_TYPES = {
    "hotkey": str,
    "auto_paste": bool,
    "restore_clipboard": bool,
    "restore_delay_sec": float,
    "beep": bool,
    "min_duration_ms": int,
    "sample_rate": int,
}


def load_config(path: str) -> Config:
    if not os.path.isfile(path):
        return Config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"config.yaml 语法错误: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(f"config.yaml 必须以 UTF-8 编码保存: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config.yaml 顶层必须是键值映射")
    values = {}
    for key, typ in _FIELD_TYPES.items():
        if key in raw and raw[key] is not None:
            value = raw[key]
            if typ is float and isinstance(value, int):
                value = float(value)
            if not isinstance(value, typ) or isinstance(value, bool) != (typ is bool):
                raise ConfigError(
                    f"配置项 {key} 期望 {typ.__name__}，实际为 {value!r}"
                )
            values[key] = value
    return Config(**values)
