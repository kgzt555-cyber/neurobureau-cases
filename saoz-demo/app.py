"""Демо конвейера обработки заявок: приём → извлечение → предквалификация → вердикт."""
from __future__ import annotations

import html
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

from engine import ENTER, REJECT, REVIEW, load_rules, qualify
from extract import extract

HERE = Path(__file__).parent
UPLOADS = HERE / "storage" / "uploads"
app = FastAPI(title="Конвейер обработки заявок — демо")

CSS = """
*{box-sizing:border-box} body{margin:0;background:#f4f5f8;color:#1a1d26;
font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:24px;letter-spacing:-.02em;margin:0 0 6px}
.sub{color:#6b7183;margin:0 0 24px;font-size:14px}
.card{background:#fff;border:1px solid #e2e5ee;border-radius:12px;padding:20px;margin-bottom:14px}
label{display:block;font-weight:600;font-size:13px;margin-bottom:6px}
input,textarea{width:100%;padding:11px 13px;border:1px solid #d7dbe6;border-radius:9px;
font:inherit;margin-bottom:16px;background:#fff}
textarea{min-height:88px;resize:vertical}
button{width:100%;padding:14px;border:0;border-radius:9px;background:#2f5bea;color:#fff;
font:600 15px inherit;cursor:pointer}
.verdict{padding:18px;border-radius:12px;margin-bottom:16px;color:#fff}
.v-enter{background:#128a4d} .v-review{background:#b7791f} .v-reject{background:#c0392b}
.verdict b{font-size:21px;display:block;margin-bottom:4px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid #eceff5;vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:#6b7183}
.tag{font:12px ui-monospace,Menlo,monospace;padding:2px 7px;border-radius:5px;white-space:nowrap}
.t-passed{background:#e3f6ec;color:#128a4d} .t-failed{background:#fdeaea;color:#c0392b}
.t-unknown{background:#fdf3e0;color:#b7791f}
.src{color:#8b91a3;font-size:12px}
.meta{color:#6b7183;font-size:13px;margin-top:14px}
a{color:#2f5bea}
"""

FORM = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Конвейер обработки заявок — демо</title><style>{css}</style></head><body><div class="wrap">
<h1>Заявка на сделку</h1>
<p class="sub">Демо конвейера: документ разбирается ИИ, правила версии {ver} выносят вердикт
с разбором по каждому фактору.</p>
<form class="card" method="post" action="/submit" enctype="multipart/form-data">
  <label>Контрагент</label>
  <input name="counterparty" placeholder="ООО «Северный Металл»" required>
  <label>Суть заявки</label>
  <textarea name="text" placeholder="Поставка металлопроката, оплата по факту"></textarea>
  <label>Документы (PDF)</label>
  <input type="file" name="files" accept="application/pdf" multiple required>
  <button type="submit">Отправить на предквалификацию</button>
</form>
</div></body></html>"""


def esc(v) -> str:
    return html.escape("—" if v is None else str(v))


def factor_rows(factors: list[dict]) -> str:
    tags = {"passed": "выполнен", "failed": "не выполнен", "unknown": "не извлечено"}
    rows = []
    for f in factors:
        pts = f" (+{f['points']})" if f.get("points") and f["status"] == "passed" else ""
        rows.append(
            f"<tr><td>{esc(f['name'])}{pts}</td>"
            f"<td>{esc(f['value'])}<br><span class='src'>{esc(f['source'] or 'источник не найден')}</span></td>"
            f"<td><span class='tag t-{f['status']}'>{tags[f['status']]}</span></td></tr>"
        )
    return "".join(rows)


@app.get("/", response_class=HTMLResponse)
def form() -> str:
    return FORM.format(css=CSS, ver=load_rules()["version"])


@app.post("/submit", response_class=HTMLResponse)
async def submit(
    counterparty: str = Form(...),
    text: str = Form(""),
    files: list[UploadFile] = File(...),
) -> str:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    profile: dict = {}
    cached = False
    for upload in files:
        data = await upload.read()
        path = UPLOADS / upload.filename
        path.write_bytes(data)
        got = extract(path, data)
        cached = cached or got.pop("_cached", False)
        # первый непустой источник выигрывает: данные из нескольких файлов не затирают друг друга
        for key, entry in got.items():
            if profile.get(key, {}).get("value") is None:
                profile[key] = entry

    result = qualify(profile)
    css_class = {ENTER: "v-enter", REVIEW: "v-review", REJECT: "v-reject"}[result["verdict"]]

    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Результат предквалификации</title><style>{CSS}</style></head><body><div class="wrap">
<h1>Заявка обработана</h1>
<p class="sub">{esc(counterparty)}{' · ' + esc(text) if text else ''}</p>

<div class="verdict {css_class}"><b>{esc(result['verdict'])}</b>{esc(result['reason'])}</div>

<div class="card">
  <table><tr><th>Критический фактор</th><th>Значение и источник</th><th>Итог</th></tr>
  {factor_rows(result['critical'])}</table>
</div>

<div class="card">
  <table><tr><th>Балльный фактор</th><th>Значение и источник</th><th>Итог</th></tr>
  {factor_rows(result['scored'])}</table>
</div>

<div class="card">
  <table><tr><th>Поле профиля</th><th>Значение</th></tr>
  <tr><td>Поставщик</td><td>{esc(profile.get('supplier', {}).get('value'))}</td></tr>
  <tr><td>ИНН</td><td>{esc(profile.get('inn', {}).get('value'))}</td></tr>
  <tr><td>Всего к оплате</td><td>{esc(profile.get('total', {}).get('value'))}</td></tr>
  <tr><td>НДС</td><td>{esc(profile.get('vat', {}).get('value'))}</td></tr>
  </table>
</div>

<p class="meta">Баллов: {result['points']} · правила {esc(result['rules_version'])}
{' · извлечение взято из кэша по хешу файла, модель повторно не вызывалась' if cached else ''}
<br>Версия правил сохраняется вместе с вердиктом: заявка останется объяснимой и после того,
как правила поменяют.</p>
<p><a href="/">← Новая заявка</a></p>
</div></body></html>"""
