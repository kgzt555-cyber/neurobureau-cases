from engine import (
    ENTER,
    REJECT,
    REVIEW,
    find_conflicts,
    load_rules,
    qualify,
    qualify_documents,
)

RULES = load_rules()


def profile(file="счёт.pdf", **kw):
    base = {"inn": "7714236589", "total": 120360, "vat": 20060, "items_count": 3}
    base.update(kw)
    out = {k: {"value": v, "source": f"{file}, стр. 1"} for k, v in base.items()}
    out["_file"] = file
    return out


def test_good_deal_enters():
    r = qualify(profile(), RULES)
    assert r["verdict"] == ENTER
    assert r["points"] == 7


def test_over_limit_rejected_by_critical():
    r = qualify(profile(total=900000), RULES)
    assert r["verdict"] == REJECT
    assert r["reason"].startswith("не выполнен критический")


def test_unreadable_critical_goes_to_human_not_rejected():
    """Главное правило демо: пустое значение не равно невыполненному критерию."""
    r = qualify(profile(inn=None), RULES)
    assert r["verdict"] == REVIEW
    assert next(c for c in r["critical"] if c["id"] == "inn_found")["status"] == "unknown"


def test_empty_string_counts_as_not_extracted():
    """Модель часто возвращает "" вместо null — это тоже «не извлекли»."""
    r = qualify(profile(inn="   "), RULES)
    assert r["verdict"] == REVIEW


def test_wrong_type_does_not_crash_and_goes_to_human():
    """Строка вместо числа не должна ронять движок пятисоткой."""
    r = qualify(profile(total="сто двадцать тысяч"), RULES)
    assert r["verdict"] == REVIEW
    assert next(c for c in r["critical"] if c["id"] == "amount_limit")["status"] == "unknown"


def test_borderline_goes_to_human():
    assert qualify(profile(total=40000, vat=0, items_count=3), RULES)["verdict"] == REJECT
    assert qualify(profile(total=40000, vat=5000, items_count=3), RULES)["verdict"] == REVIEW


def test_verdict_carries_rules_version():
    assert qualify(profile(), RULES)["rules_version"] == RULES["version"]


def test_second_document_cannot_close_missing_inn():
    """Ключевая защита: ИНН из чужого счёта не закрывает критический фактор заявки."""
    kp = profile(file="кп.pdf", inn=None, total=360000, vat=0, items_count=2)
    schet = profile(file="счёт.pdf")
    r = qualify_documents([kp, schet], RULES)
    assert r["verdict"] == REVIEW


def test_second_document_over_limit_is_not_hidden():
    """Лимит проверяется по каждому документу, а не по первому непустому значению."""
    small = profile(file="счёт-1.pdf", total=120360)
    huge = profile(file="счёт-2.pdf", total=5000000)
    assert qualify_documents([small, huge], RULES)["verdict"] == REJECT


def test_conflicting_counterparties_go_to_human():
    a = profile(file="а.pdf", inn="7714236589")
    b = profile(file="б.pdf", inn="7811556420")
    r = qualify_documents([a, b], RULES)
    assert r["verdict"] == REVIEW
    assert r["reason"] == "документы относятся к разным контрагентам"
    assert find_conflicts([a, b])[0]["field"] == "inn"


def test_single_clean_document_still_enters():
    assert qualify_documents([profile()], RULES)["verdict"] == ENTER
