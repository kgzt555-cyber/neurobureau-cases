"""Извлечение профиля заявки из приложенных документов.

Каждое значение тащит с собой источник: файл и страницу. Без этого разбор
факторов показывает «сумма 4,2 млн → минус 3 балла» и не показывает, откуда
взялись эти 4,2 млн — и первый же спор превращается в ручную перепроверку.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

HERE = Path(__file__).parent
load_dotenv(HERE.parent / ".env")

CACHE_PATH = HERE / "storage" / "extraction_cache.json"

PROMPT = """Из текста документа вытащи поля заявки. Верни СТРОГО JSON:

{
  "inn": "ИНН строкой или null",
  "total": число (всего к оплате) или null,
  "vat": число (сумма НДС, 0 если не облагается) или null,
  "items_count": число позиций или null,
  "supplier": "поставщик или null"
}

Если поля в документе нет — ставь null. Ничего не выдумывай: пустое значение
безопаснее правдоподобной догадки, потому что по этим числам выносится решение
о сделке.

Текст документа:
"""


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def pdf_text(path: Path) -> tuple[str, int]:
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text, len(reader.pages)


def extract(path: Path, data: bytes) -> dict:
    """Профиль заявки. Повтор по тому же файлу берёт кэш, а не зовёт модель заново:
    иначе ретрай после таймаута вернёт другие числа и другой вердикт."""
    digest = file_hash(data)
    cache = _cache()
    if digest in cache:
        return {**cache[digest], "_cached": True}

    text, pages = pdf_text(path)
    client = OpenAI(
        api_key=os.environ["AI_API_KEY"],
        base_url=os.environ.get("AI_BASE_URL", "https://api.proxyapi.ru/openai/v1"),
    )
    resp = client.chat.completions.create(
        model=os.environ.get("AI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": PROMPT + text[:12000]}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    raw = json.loads(resp.choices[0].message.content)

    source = f"{path.name}, стр. 1–{pages}" if pages > 1 else path.name
    profile = {
        key: {"value": raw.get(key), "source": source if raw.get(key) is not None else None}
        for key in ("inn", "total", "vat", "items_count", "supplier")
    }
    cache[digest] = profile
    _save_cache(cache)
    return {**profile, "_cached": False}
