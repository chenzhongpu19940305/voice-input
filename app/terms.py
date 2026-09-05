"""术语表加载与识别结果后处理替换。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import yaml


class TermsError(Exception):
    """术语表无法解析或正则非法。"""


@dataclass(frozen=True)
class TermRule:
    pattern: str
    replacement: str
    regex: bool = False


def load_terms(path: str) -> list[TermRule]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise TermsError(f"terms.yaml 语法错误: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise TermsError(f"terms.yaml 必须以 UTF-8 编码保存: {exc}") from exc
    if not isinstance(raw, dict):
        raise TermsError("terms.yaml 顶层必须是键值映射")
    entries = raw.get("rules") or []
    rules: list[TermRule] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict) or "pattern" not in entry or "replacement" not in entry:
            raise TermsError(f"terms.yaml 第 {i + 1} 条规则缺少 pattern/replacement")
        rule = TermRule(
            pattern=str(entry["pattern"]),
            replacement=str(entry["replacement"]),
            regex=bool(entry.get("regex", False)),
        )
        if rule.regex:
            try:
                re.compile(rule.pattern)
            except re.error as exc:
                raise TermsError(f"terms.yaml 第 {i + 1} 条正则非法: {exc}") from exc
        rules.append(rule)
    return rules


def apply_terms(text: str, rules: list[TermRule]) -> str:
    result = text
    for rule in rules:
        if rule.regex:
            result = re.sub(rule.pattern, rule.replacement, result)
        else:
            result = result.replace(rule.pattern, rule.replacement)
    return result
