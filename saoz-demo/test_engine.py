from engine import ENTER, REJECT, REVIEW, load_rules, qualify

RULES = load_rules()


def profile(**kw):
    base = {"inn": 7714236589, "total": 120360, "vat": 20060, "items_count": 3}
    base.update(kw)
    return {k: {"value": v, "source": "счёт.pdf, стр. 1"} for k, v in base.items()}


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
    inn = next(c for c in r["critical"] if c["id"] == "inn_found")
    assert inn["status"] == "unknown"


def test_unknown_scored_factor_does_not_add_points():
    r = qualify(profile(vat=None), RULES)
    assert r["points"] == 5
    assert r["verdict"] == ENTER


def test_borderline_goes_to_human():
    r = qualify(profile(total=40000, vat=0, items_count=3), RULES)
    assert r["points"] == 2
    assert r["verdict"] == REJECT

    r2 = qualify(profile(total=40000, vat=5000, items_count=3), RULES)
    assert r2["points"] == 4
    assert r2["verdict"] == REVIEW


def test_verdict_carries_rules_version():
    assert qualify(profile(), RULES)["rules_version"] == RULES["version"]


def test_every_factor_carries_source():
    r = qualify(profile(), RULES)
    for f in r["critical"] + r["scored"]:
        assert f["source"] == "счёт.pdf, стр. 1"
