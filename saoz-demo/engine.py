"""Движок предквалификации: критические и балльные факторы, три исхода.

Два решения, ради которых демо и сделано:
1. Вердикт хранит версию правил, по которой его посчитали.
2. «Не смогли извлечь» и «не соответствует критерию» — разные исходы.
   Если их схлопнуть, заявка с плохо распознанным сканом наберёт проходной балл.
"""
from __future__ import annotations

import json
from pathlib import Path

RULES_PATH = Path(__file__).parent / "rules.json"

ENTER = "входить"
REVIEW = "требует человека"
REJECT = "не входить"


def load_rules(path: Path = RULES_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _compare(value, check: str, expected) -> bool:
    if check == "not_empty":
        return value not in (None, "", [])
    if check == "lte":
        return value <= expected
    if check == "gte":
        return value >= expected
    if check == "gt":
        return value > expected
    raise ValueError(f"неизвестная проверка: {check}")


def _evaluate(rule: dict, profile: dict) -> dict:
    """Три исхода вместо двух: passed, failed, unknown."""
    entry = profile.get(rule["field"])
    value = entry.get("value") if isinstance(entry, dict) else entry
    source = entry.get("source") if isinstance(entry, dict) else None

    if value is None:
        return {**rule, "status": "unknown", "value": None, "source": source}
    status = "passed" if _compare(value, rule["check"], rule.get("value")) else "failed"
    return {**rule, "status": status, "value": value, "source": source}


def qualify(profile: dict, rules: dict | None = None) -> dict:
    rules = rules or load_rules()

    critical = [_evaluate(r, profile) for r in rules["critical"]]
    scored = [_evaluate(r, profile) for r in rules["scored"]]
    points = sum(r["points"] for r in scored if r["status"] == "passed")

    if any(r["status"] == "failed" for r in critical):
        verdict, reason = REJECT, "не выполнен критический фактор"
    elif any(r["status"] == "unknown" for r in critical):
        # ключевое место: пустое значение не приравнивается к невыполнению
        verdict, reason = REVIEW, "критический фактор не удалось извлечь из документов"
    elif points >= rules["thresholds"]["enter"]:
        verdict, reason = ENTER, f"набрано {points} баллов при пороге {rules['thresholds']['enter']}"
    elif points >= rules["thresholds"]["review"]:
        verdict, reason = REVIEW, f"набрано {points} баллов, это пограничная зона"
    else:
        verdict, reason = REJECT, f"набрано {points} баллов, порог не пройден"

    return {
        "verdict": verdict,
        "reason": reason,
        "points": points,
        "rules_version": rules["version"],
        "critical": critical,
        "scored": scored,
    }
