"""Извлечение профиля заявки из приложенного документа.

Каждое значение тащит с собой источник: файл и страницу. Без этого разбор
факторов показывает «сумма 360 000 → +3 балла» и не показывает, откуда
взялась сумма — первый же спор превращается в ручную перепроверку пакета.
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
NUMERIC = ("total", "vat", "items_count")

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


class DocumentError(Exception):
    """Файл не удалось прочитать как PDF с текстовым слоем."""


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


def _number(value):
    """Модель может вернуть 120360, '120360' или '120 360,00'. Всё, что не число, — None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    cleaned = str(value).replace(" ", "").replace(" ", "").replace(",", ".")
    cleaned = "".join(c for c in cleaned if c.isdigit() or c in ".-")
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else None
    except ValueError:
        return None


def _text_or_none(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def pdf_text(path: Path) -> tuple[str, int]:
    try:
        reader = PdfReader(path)
        pages = len(reader.pages)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:  # битый файл, не-PDF, зашифрованный — всё сюда
        raise DocumentError(str(e)) from e
    if not text.strip():
        raise DocumentError("в файле нет текстового слоя, нужен OCR")
    return text, pages


def extract(path: Path, data: bytes, display_name: str | None = None) -> dict:
    """Профиль документа. Повтор по тому же файлу берёт кэш, а не зовёт модель:
    иначе ретрай после таймаута вернёт другие числа и другой вердикт."""
    name = display_name or path.name
    digest = file_hash(data)
    cache = _cache()
    if digest in cache:
        cached = json.loads(json.dumps(cache[digest]))  # копия, чтобы не портить кэш
        for entry in cached.values():
            if isinstance(entry, dict) and entry.get("source"):
                entry["source"] = name  # источник — имя текущей загрузки, не прошлой
        return {**cached, "_file": name, "_cached": True}

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
    content = resp.choices[0].message.content.strip().strip("`")
    if content.startswith("json"):
        content = content[4:]
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as e:
        raise DocumentError(f"модель вернула не JSON: {e}") from e

    values = {
        key: (_number(raw.get(key)) if key in NUMERIC else _text_or_none(raw.get(key)))
        for key in ("inn", "total", "vat", "items_count", "supplier")
    }
    source = f"стр. 1–{pages}" if pages > 1 else "стр. 1"
    profile = {
        key: {"value": val, "source": f"{name}, {source}" if val is not None else None}
        for key, val in values.items()
    }
    cache[digest] = profile
    _save_cache(cache)
    return {**profile, "_file": name, "_cached": False}
