"""Демо конвейера обработки заявок: приём → извлечение → предквалификация → вердикт."""
from __future__ import annotations

import html
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse

from engine import ENTER, REJECT, REVIEW, load_rules, qualify_documents
from extract import DocumentError, extract, file_hash

HERE = Path(__file__).parent
UPLOADS = HERE / "storage" / "uploads"
MAX_BYTES = 20 * 1024 * 1024

app = FastAPI(title="Конвейер обработки заявок — демо")

CSS = """
*{box-sizing:border-box} body{margin:0;background:#f4f5f8;color:#1a1d26;
font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:24px;letter-spacing:-.02em;margin:0 0 6px}
h2{font-size:15px;margin:22px 0 10px}
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
.warn{background:#fdf3e0;border:1px solid #f0d9a8;border-radius:10px;padding:13px 15px;
margin-bottom:14px;font-size:14px}
.doc{font:12px ui-monospace,Menlo,monospace;color:#6b7183;margin-bottom:8px}
a{color:#2f5bea}
"""

PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head><body><div class="wrap">{body}</div></body></html>"""


def page(title: str, body: str) -> str:
    return PAGE.format(title=html.escape(title), css=CSS, body=body)


def esc(v) -> str:
    return html.escape("—" if v is None else str(v))


def money(v) -> str:
    """120360.0 в отчёте о сделке читается как небрежность."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return esc(v)
    if float(v).is_integer():
        return f"{int(v):,}".replace(",", " ")
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def factor_rows(factors: list[dict]) -> str:
    tags = {"passed": "выполнен", "failed": "не выполнен", "unknown": "не извлечено"}
    rows = []
    for f in factors:
        pts = f" (+{f['points']})" if f.get("points") and f["status"] == "passed" else ""
        rows.append(
            f"<tr><td>{esc(f['name'])}{pts}</td>"
            f"<td>{money(f['value'])}<br><span class='src'>{esc(f['source'] or 'источник не найден')}</span></td>"
            f"<td><span class='tag t-{f['status']}'>{tags[f['status']]}</span></td></tr>"
        )
    return "".join(rows)


@app.get("/", response_class=HTMLResponse)
def form() -> str:
    return page(
        "Конвейер обработки заявок — демо",
        f"""<h1>Заявка на сделку</h1>
<p class="sub">Демо конвейера: документы разбираются ИИ, правила версии
{esc(load_rules()['version'])} выносят вердикт с разбором по каждому фактору.</p>
<form class="card" method="post" action="/submit" enctype="multipart/form-data">
  <label>Контрагент</label>
  <input name="counterparty" placeholder="ООО «Северный Металл»" required>
  <label>Суть заявки</label>
  <textarea name="text" placeholder="Поставка металлопроката, оплата по факту"></textarea>
  <label>Документы (PDF с текстовым слоем)</label>
  <input type="file" name="files" accept="application/pdf" multiple required>
  <button type="submit">Отправить на предквалификацию</button>
</form>""",
    )


@app.post("/submit", response_class=HTMLResponse)
async def submit(
    counterparty: str = Form(...),
    text: str = Form(""),
    files: list[UploadFile] = File(...),
) -> str:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    profiles: list[dict] = []
    problems: list[str] = []
    cached = False

    for upload in files:
        shown = Path(upload.filename or "документ.pdf").name or "документ.pdf"
        data = await upload.read()
        if len(data) > MAX_BYTES:
            problems.append(f"{shown}: файл больше 20 МБ")
            continue
        # имя от клиента в путь не попадает: иначе «../../rules.json» перезапишет правила
        path = UPLOADS / f"{file_hash(data)}.pdf"
        path.write_bytes(data)
        try:
            # синхронное извлечение уводим из event loop, иначе сервер замирает целиком
            got = await run_in_threadpool(extract, path, data, shown)
        except DocumentError as e:
            problems.append(f"{shown}: {e}")
            continue
        cached = cached or got.pop("_cached", False)
        profiles.append(got)

    if not profiles:
        return page(
            "Заявка не обработана",
            "<h1>Не смог прочитать документы</h1>"
            + "".join(f"<div class='warn'>{esc(p)}</div>" for p in problems)
            + "<p class='meta'>Демо читает PDF с текстовым слоем. Скан без распознавания "
            "или файл другого формата разобрать нечем — в такой ситуации заявка уходит "
            "человеку, а не получает автоматический отказ.</p>"
            "<p><a href='/'>← Новая заявка</a></p>",
        )

    result = qualify_documents(profiles)
    css_class = {ENTER: "v-enter", REVIEW: "v-review", REJECT: "v-reject"}[result["verdict"]]

    blocks = []
    for doc in result["documents"]:
        head = f"<div class='doc'>{esc(doc['doc'])} · {esc(doc['verdict'])} · {doc['points']} б.</div>"
        blocks.append(
            f"<div class='card'>{head}"
            f"<table><tr><th>Критический фактор</th><th>Значение и источник</th><th>Итог</th></tr>"
            f"{factor_rows(doc['critical'])}</table>"
            f"<table style='margin-top:14px'><tr><th>Балльный фактор</th><th>Значение и источник</th><th>Итог</th></tr>"
            f"{factor_rows(doc['scored'])}</table></div>"
        )

    warns = "".join(f"<div class='warn'>{esc(p)}</div>" for p in problems)
    for c in result["conflicts"]:
        values = ", ".join(f"{esc(v)} ({esc(s)})" for v, s in c["values"].items())
        warns += (
            f"<div class='warn'>Разные значения поля «{esc(c['field'])}» в документах: {values}. "
            "Похоже, приложены документы разных контрагентов.</div>"
        )

    return page(
        "Результат предквалификации",
        f"""<h1>Заявка обработана</h1>
<p class="sub">{esc(counterparty)}{' · ' + esc(text) if text else ''}</p>
<div class="verdict {css_class}"><b>{esc(result['verdict'])}</b>{esc(result['reason'])}</div>
{warns}
<h2>Разбор по документам</h2>
{''.join(blocks)}
<p class="meta">Правила {esc(result['rules_version'])}. Версия сохраняется вместе с вердиктом:
заявка останется объяснимой и после того, как правила поменяют.
{' Извлечение взято из кэша по хешу файла, модель повторно не вызывалась.' if cached else ''}
<br>Каждый документ считается отдельно: иначе ИНН из приложенного счёта чужой компании
закрыл бы критический фактор по этой заявке.</p>
<p><a href="/">← Новая заявка</a></p>""",
    )
