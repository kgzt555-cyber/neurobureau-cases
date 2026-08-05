"""Локальный эквивалент Cloudflare Worker — тот же контракт, тот же промпт.

Нужен, чтобы проверить виджет целиком с настоящей моделью до появления
аккаунта Cloudflare. Ключ читается из ../.env и в браузер не попадает.

Запуск: python3 proxy_local.py  (слушает http://localhost:8787/chat)
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).parent

# .env лежит в корне репозитория кейсов
for line in (HERE.parent / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

from openai import OpenAI  # noqa: E402  (после загрузки .env)

MAX_MESSAGES = 20
MAX_CONTENT = 500

SYSTEM_PROMPT = (
    "Ты консультант столярной мастерской «Дубрава» на её сайте.\n"
    "Отвечай по-русски, коротко: два-четыре предложения, без списков и канцелярита.\n"
    "Отвечай только по базе знаний ниже. Если ответа в ней нет — скажи честно\n"
    "и предложи написать в форму на сайте. Цены не называй: по базе они считаются\n"
    "по эскизу. Не выдумывай услуги, сроки и факты. На вопросы не о мастерской\n"
    "вежливо возвращай разговор к делу.\n\n--- БАЗА ЗНАНИЙ ---\n"
    + (HERE / "knowledge.md").read_text(encoding="utf-8")
)

client = OpenAI(api_key=os.environ["AI_API_KEY"], base_url=os.environ["AI_BASE_URL"])
MODEL = os.environ.get("AI_MODEL", "gpt-4o-mini")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # тихий лог
        print(self.address_string(), fmt % args)

    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(200, {})

    def do_POST(self):
        if self.path != "/chat":
            self._send(404, {"error": "not found"})
            return
        try:
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            incoming = json.loads(raw).get("messages", [])
        except (ValueError, KeyError):
            self._send(400, {"error": "bad json"})
            return

        messages = [
            {"role": m["role"], "content": str(m.get("content", ""))[:MAX_CONTENT]}
            for m in incoming
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ][-MAX_MESSAGES:]
        if not messages or messages[-1]["role"] != "user":
            self._send(400, {"error": "no user message"})
            return

        try:
            resp = client.chat.completions.create(
                model=MODEL,
                temperature=0.4,
                max_tokens=400,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            )
            self._send(200, {"reply": (resp.choices[0].message.content or "").strip()})
        except Exception as e:  # честная 502, как в воркере
            print("upstream error:", e)
            self._send(502, {"error": "upstream"})


if __name__ == "__main__":
    print("прокси слушает http://localhost:8787/chat")
    HTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
