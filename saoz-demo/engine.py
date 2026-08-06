"""Движок предквалификации: критические и балльные факторы, три исхода.

Три решения, ради которых демо и сделано:
1. Вердикт хранит версию правил, по которой его посчитали.
2. «Не смогли извлечь» и «не соответствует критерию» — разные исходы.
   Если их схлопнуть, заявка с плохо распознанным сканом наберёт проходной балл.
3. Документы не сливаются в один профиль: каждый считается отдельно, иначе
   ИНН из чужого счёта закроет критический фактор по этой заявке.
"""
from __future__ import annotations

import json
from pathlib import Path

RULES_PATH = Path(__file__).parent / "rules.json"

ENTER = "входить"
REVIEW = "требует человека"
REJECT = "не входить"

# от мягкого к строгому: итог по заявке — самый строгий из вердиктов по документам
SEVERITY = {ENTER: 0, REVIEW: 1, REJECT: 2}


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


def _is_blank(value) -> bool:
    """Пустая строка от модели значит то же, что null: значение не извлеклось."""
    return value is None or (isinstance(value, str) and not value.strip())


def _evaluate(rule: dict, profile: dict) -> dict:
    """Три исхода: passed, failed, unknown."""
    entry = profile.get(rule["field"])
    value = entry.get("value") if isinstance(entry, dict) else entry
    source = entry.get("source") if isinstance(entry, dict) else None
    out = {**rule, "value": value, "source": source}

    if _is_blank(value):
        return {**out, "status": "unknown"}
    try:
        status = "passed" if _compare(value, rule["check"], rule.get("value")) else "failed"
    except TypeError:
        # значение пришло не того типа — это тоже «не извлекли», а не «не выполнил»
        return {**out, "status": "unknown"}
    return {**out, "status": status}


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


def find_conflicts(profiles: list[dict]) -> list[dict]:
    """Разные значения одного поля в разных документах.

    Заявка на одну сделку не может иметь два ИНН. Если такое случилось —
    документы относятся к разным контрагентам, и решать это должен человек.
    """
    conflicts = []
    for field in ("inn", "supplier"):
        seen: dict[str, str] = {}
        for prof in profiles:
            entry = prof.get(field) or {}
            value = entry.get("value")
            if _is_blank(value):
                continue
            seen.setdefault(str(value).strip(), entry.get("source") or "?")
        if len(seen) > 1:
            conflicts.append({"field": field, "values": seen})
    return conflicts


def qualify_documents(profiles: list[dict], rules: dict | None = None) -> dict:
    """Вердикт по заявке: каждый документ считается сам по себе.

    Слить поля из всех файлов в один профиль — заманчиво и опасно: ИНН из
    приложенного счёта другой компании закроет критический фактор, а сумма
    из первого документа скроет превышение лимита во втором.
    """
    rules = rules or load_rules()
    per_doc = [{**qualify(p, rules), "doc": (p.get("_file") or "документ")} for p in profiles]
    conflicts = find_conflicts(profiles)

    strictest = max(per_doc, key=lambda r: SEVERITY[r["verdict"]])
    verdict, reason = strictest["verdict"], strictest["reason"]

    if conflicts and SEVERITY[verdict] < SEVERITY[REVIEW]:
        verdict = REVIEW
        reason = "документы относятся к разным контрагентам"
    elif len(per_doc) > 1 and SEVERITY[verdict] > 0:
        reason = f"{reason} (документ: {strictest['doc']})"

    return {
        "verdict": verdict,
        "reason": reason,
        "rules_version": rules["version"],
        "documents": per_doc,
        "conflicts": conflicts,
    }
