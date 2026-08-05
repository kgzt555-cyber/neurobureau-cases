/* Виджет-консультант для сайта.
   Подключение одной строкой:
   <script src="widget.js" data-proxy="https://ваш-воркер.workers.dev/chat" data-title="Консультант"></script>
   Ключа модели здесь нет и быть не может: запросы идут через прокси. */
(function () {
  var script = document.currentScript;
  var PROXY = script.getAttribute("data-proxy") || "";
  var TITLE = script.getAttribute("data-title") || "Консультант";
  var MAX_LEN = 500;
  var MAX_TURNS = 20;

  var history = []; // {role, content}
  var busy = false;

  var css =
    "#nbw-bubble{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border:none;border-radius:50%;" +
    "background:#4f46e5;color:#fff;font-size:24px;cursor:pointer;box-shadow:0 6px 18px rgba(0,0,0,.25);z-index:99998}" +
    "#nbw-box{position:fixed;right:20px;bottom:88px;width:340px;max-width:calc(100vw - 40px);height:440px;" +
    "max-height:calc(100vh - 120px);display:none;flex-direction:column;background:#fff;border-radius:14px;" +
    "box-shadow:0 12px 40px rgba(0,0,0,.3);overflow:hidden;z-index:99999;font:14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}" +
    "#nbw-box.open{display:flex}" +
    "#nbw-head{background:#4f46e5;color:#fff;padding:12px 14px;font-weight:600}" +
    "#nbw-log{flex:1;overflow-y:auto;padding:12px;background:#f6f7fb}" +
    ".nbw-msg{max-width:85%;margin:0 0 8px;padding:8px 11px;border-radius:11px;white-space:pre-wrap;word-wrap:break-word}" +
    ".nbw-user{background:#4f46e5;color:#fff;margin-left:auto;border-bottom-right-radius:4px}" +
    ".nbw-bot{background:#fff;color:#1c1c28;border:1px solid #e3e5ef;border-bottom-left-radius:4px}" +
    ".nbw-wait{color:#8a8fa3;font-style:italic}" +
    "#nbw-form{display:flex;border-top:1px solid #e3e5ef}" +
    "#nbw-inp{flex:1;border:none;padding:12px;font:inherit;outline:none}" +
    "#nbw-send{border:none;background:none;color:#4f46e5;font-weight:600;padding:0 14px;cursor:pointer}";

  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  var bubble = document.createElement("button");
  bubble.id = "nbw-bubble";
  bubble.type = "button";
  bubble.textContent = "💬";
  bubble.setAttribute("aria-label", "Открыть чат с консультантом");

  var box = document.createElement("div");
  box.id = "nbw-box";
  box.innerHTML =
    '<div id="nbw-head"></div><div id="nbw-log"></div>' +
    '<form id="nbw-form"><input id="nbw-inp" maxlength="' + MAX_LEN + '" ' +
    'placeholder="Ваш вопрос…" autocomplete="off"><button id="nbw-send" type="submit">→</button></form>';
  document.body.appendChild(bubble);
  document.body.appendChild(box);

  box.querySelector("#nbw-head").textContent = TITLE;
  var log = box.querySelector("#nbw-log");
  var form = box.querySelector("#nbw-form");
  var inp = box.querySelector("#nbw-inp");

  function add(cls, text) {
    var el = document.createElement("div");
    el.className = "nbw-msg " + cls;
    el.textContent = text; // только textContent — разметка из ответов не исполняется
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  bubble.addEventListener("click", function () {
    box.classList.toggle("open");
    if (box.classList.contains("open") && !log.children.length) {
      add("nbw-bot", "Здравствуйте! Отвечу на вопросы о мастерской: услуги, сроки, материалы, доставка.");
      inp.focus();
    }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var q = inp.value.trim();
    if (!q || busy) return;
    if (history.length >= MAX_TURNS * 2) {
      add("nbw-bot", "Длинный получился разговор. Обновите страницу, чтобы начать заново.");
      return;
    }
    inp.value = "";
    add("nbw-user", q);
    history.push({ role: "user", content: q.slice(0, MAX_LEN) });

    var wait = add("nbw-bot nbw-wait", "Печатает…");
    busy = true;

    fetch(PROXY, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("proxy " + r.status);
        return r.json();
      })
      .then(function (d) {
        wait.remove();
        var reply = String(d.reply || "").trim() || "Не получилось ответить, попробуйте ещё раз.";
        add("nbw-bot", reply);
        history.push({ role: "assistant", content: reply });
      })
      .catch(function () {
        wait.remove();
        add("nbw-bot", "Не дозвонился до сервера. Попробуйте через минуту.");
        history.pop(); // вопрос не дошёл — не держим его в истории
      })
      .finally(function () {
        busy = false;
      });
  });
})();
