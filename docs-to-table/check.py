"""Сверка разобранных счетов с эталоном.

Смысл кейса не в том, что скрипт что-то выдал, а в том, что выданное совпадает
с документом. Здесь это измеряется, а не декларируется.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
FIELDS = ["number", "date", "supplier", "inn", "vat_rate", "subtotal", "vat", "total"]


def norm(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return " ".join(str(value).split()).strip().strip('"').lower()


def main() -> None:
    expected = json.loads((HERE / "samples" / "expected.json").read_text(encoding="utf-8"))
    parsed = json.loads((HERE / "output" / "parsed.json").read_text(encoding="utf-8"))
    by_file = {p.get("file"): p for p in parsed}

    checks = errors = 0
    for exp in expected:
        got = by_file.get(exp["file"])
        if got is None:
            print(f"НЕ РАЗОБРАН: {exp['file']}")
            errors += len(FIELDS)
            checks += len(FIELDS)
            continue
        for field in FIELDS:
            checks += 1
            if norm(exp.get(field)) != norm(got.get(field)):
                errors += 1
                print(f"{exp['file']} → {field}: ждали {exp.get(field)!r}, "
                      f"получили {got.get(field)!r}")

        exp_items = exp["items"]
        got_items = got.get("items") or []
        checks += 1
        if len(exp_items) != len(got_items):
            errors += 1
            print(f"{exp['file']} → позиций: ждали {len(exp_items)}, "
                  f"получили {len(got_items)}")
        else:
            for e_item, g_item in zip(exp_items, got_items):
                for key in ("name", "qty", "price"):
                    checks += 1
                    if norm(e_item[key]) != norm(g_item.get(key)):
                        errors += 1
                        print(f"{exp['file']} → позиция {key}: "
                              f"ждали {e_item[key]!r}, получили {g_item.get(key)!r}")

    ok = checks - errors
    print(f"\nсовпало {ok} из {checks} значений ({ok / checks * 100:.1f}%)")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
