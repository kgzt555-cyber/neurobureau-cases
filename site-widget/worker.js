/* Cloudflare Worker — прокси между виджетом и моделью.
   Зачем он нужен: ключ модели нельзя класть в браузерный код — его увидит
   любой посетитель и сожжёт баланс. Ключ живёт здесь, в секретах воркера.

   Деплой через веб-интерфейс Cloudflare (без командной строки):
   1. Dashboard → Workers & Pages → Create Worker → вставить этот файл целиком.
   2. Settings → Variables and Secrets:
      AI_API_KEY (secret) — ключ прокси-сервиса модели
      AI_BASE_URL — https://api.proxyapi.ru/openai/v1
      AI_MODEL — gpt-4o-mini
      ALLOWED_ORIGIN — https://домен-сайта-клиента (или * на время теста)
   3. В widget.js на сайте указать data-proxy="https://имя.workers.dev/chat". */

const SYSTEM_PROMPT = `Ты консультант столярной мастерской «Дубрава» на её сайте.
Отвечай по-русски, коротко: два-четыре предложения, без списков и канцелярита.
Отвечай только по базе знаний ниже. Если ответа в ней нет — скажи честно
и предложи написать в форму на сайте. Цены не называй: по базе они считаются
по эскизу. Не выдумывай услуги, сроки и факты. На вопросы не о мастерской
вежливо возвращай разговор к делу.

--- БАЗА ЗНАНИЙ ---
{KNOWLEDGE}`;

const MAX_MESSAGES = 20;
const MAX_CONTENT = 500;

function cors(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors(env) });
    }
    if (request.method !== "POST") {
      return new Response("only POST", { status: 405, headers: cors(env) });
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "bad json" }, 400, env);
    }

    const incoming = Array.isArray(body.messages) ? body.messages : [];
    // истории верим ограниченно: роль из белого списка, длина обрезается
    const messages = incoming
      .filter((m) => m && (m.role === "user" || m.role === "assistant"))
      .slice(-MAX_MESSAGES)
      .map((m) => ({ role: m.role, content: String(m.content || "").slice(0, MAX_CONTENT) }));
    if (!messages.length || messages[messages.length - 1].role !== "user") {
      return json({ error: "no user message" }, 400, env);
    }

    const resp = await fetch(`${env.AI_BASE_URL}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${env.AI_API_KEY}`,
      },
      body: JSON.stringify({
        model: env.AI_MODEL,
        temperature: 0.4,
        max_tokens: 400,
        messages: [{ role: "system", content: SYSTEM_PROMPT }, ...messages],
      }),
    });
    if (!resp.ok) {
      return json({ error: "upstream " + resp.status }, 502, env);
    }
    const data = await resp.json();
    const reply = (data.choices?.[0]?.message?.content || "").trim();
    return json({ reply }, 200, env);
  },
};

function json(obj, status, env) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...cors(env) },
  });
}
