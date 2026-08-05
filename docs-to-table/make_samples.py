"""Генератор демонстрационных счетов в PDF.

Чужие документы в публичный кейс класть нельзя, поэтому счета выдуманные.
Заодно из тех же данных пишется expected.json — эталон, по которому
check.py потом измеряет точность разбора.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HERE = Path(__file__).parent
SAMPLES = HERE / "samples"

INVOICES = [
    {
        "number": "СЧ-2026-0417",
        "date": "12.07.2026",
        "supplier": 'ООО "Северный Металл"',
        "inn": "7714236589",
        "vat_rate": 20,
        "items": [
            {"name": "Лист стальной 2 мм", "qty": 40, "price": 1850.00},
            {"name": "Уголок 50х50", "qty": 120, "price": 320.50},
            {"name": "Доставка до склада", "qty": 1, "price": 12000.00},
        ],
    },
    {
        "number": "INV-000892",
        "date": "03.07.2026",
        "supplier": 'ИП Кузнецова А. В.',
        "inn": "504312876655",
        "vat_rate": 0,
        "items": [
            {"name": "Разработка макета упаковки", "qty": 3, "price": 8500.00},
            {"name": "Правки после согласования", "qty": 2, "price": 2500.00},
        ],
    },
    {
        "number": "СФ-7781",
        "date": "28.06.2026",
        "supplier": 'АО "ТехноСнаб"',
        "inn": "7743013901",
        "vat_rate": 20,
        "items": [
            {"name": "Картридж HP 26A", "qty": 8, "price": 6400.00},
            {"name": "Бумага А4, пачка 500 л.", "qty": 50, "price": 410.00},
            {"name": "Степлер тяжёлый", "qty": 4, "price": 1290.00},
            {"name": "Утилизация тары", "qty": 1, "price": 900.00},
        ],
    },
    {
        "number": "2026/114",
        "date": "19.07.2026",
        "supplier": 'ООО "Грузовые Линии"',
        "inn": "7811556420",
        "vat_rate": 20,
        "items": [
            {"name": "Перевозка Москва — Казань", "qty": 2, "price": 47000.00},
            {"name": "Страхование груза", "qty": 2, "price": 3150.00},
        ],
    },
    {
        "number": "СЧ-0031",
        "date": "01.08.2026",
        "supplier": 'ИП Мурадов Р. Т.',
        "inn": "056112934708",
        "vat_rate": 0,
        "items": [
            {"name": "Обслуживание кофемашин, июль", "qty": 1, "price": 24000.00},
        ],
    },
]

CSS = """
body { font-family: Helvetica, Arial, sans-serif; font-size: 12px; margin: 40px; color: #111; }
h1 { font-size: 18px; margin: 0 0 4px; }
.meta { margin-bottom: 18px; color: #333; }
.meta div { margin: 2px 0; }
table { width: 100%; border-collapse: collapse; margin-top: 10px; }
th, td { border: 1px solid #999; padding: 6px 8px; text-align: left; }
th { background: #eee; }
td.num, th.num { text-align: right; }
.totals { margin-top: 14px; width: 320px; margin-left: auto; }
.totals td { border: none; padding: 3px 0; }
.totals td.num { text-align: right; font-weight: bold; }
"""


def totals(inv: dict) -> dict:
    subtotal = round(sum(i["qty"] * i["price"] for i in inv["items"]), 2)
    vat = round(subtotal * inv["vat_rate"] / 100, 2)
    return {"subtotal": subtotal, "vat": vat, "total": round(subtotal + vat, 2)}


def money(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",")


def render_html(inv: dict) -> str:
    t = totals(inv)
    rows = "".join(
        f"<tr><td>{n}</td><td>{i['name']}</td><td class='num'>{i['qty']}</td>"
        f"<td class='num'>{money(i['price'])}</td>"
        f"<td class='num'>{money(round(i['qty'] * i['price'], 2))}</td></tr>"
        for n, i in enumerate(inv["items"], start=1)
    )
    vat_row = (
        f"<tr><td>НДС {inv['vat_rate']}%</td><td class='num'>{money(t['vat'])} руб.</td></tr>"
        if inv["vat_rate"]
        else "<tr><td>НДС</td><td class='num'>не облагается</td></tr>"
    )
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<style>{CSS}</style></head><body>
<h1>Счёт на оплату № {inv['number']}</h1>
<div class="meta">
  <div>Дата: {inv['date']}</div>
  <div>Поставщик: {inv['supplier']}</div>
  <div>ИНН: {inv['inn']}</div>
</div>
<table>
  <tr><th>№</th><th>Наименование</th><th class="num">Кол-во</th>
      <th class="num">Цена</th><th class="num">Сумма</th></tr>
  {rows}
</table>
<table class="totals">
  <tr><td>Итого без НДС</td><td class="num">{money(t['subtotal'])} руб.</td></tr>
  {vat_row}
  <tr><td>Всего к оплате</td><td class="num">{money(t['total'])} руб.</td></tr>
</table>
</body></html>"""


def main() -> None:
    SAMPLES.mkdir(exist_ok=True)
    expected = []
    for inv in INVOICES:
        stem = inv["number"].replace("/", "-")
        html_path = SAMPLES / f"{stem}.html"
        pdf_path = SAMPLES / f"{stem}.pdf"
        html_path.write_text(render_html(inv), encoding="utf-8")
        subprocess.run(
            [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf_path}", f"file://{html_path}"],
            check=True, capture_output=True,
        )
        html_path.unlink()
        expected.append({**inv, **totals(inv), "file": pdf_path.name})
        print(f"готов {pdf_path.name}")

    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{len(expected)} счетов и эталон в {SAMPLES}")


if __name__ == "__main__":
    main()
