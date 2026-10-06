/* ── Atlas — interface de communication ─────────────────────────────── */
"use strict";

const chat = document.getElementById("chat");
const empty = document.getElementById("empty");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const statusEl = document.getElementById("status");

const state = {
  busy: false,
  controller: null,
  history: [],        // [{role, content}] pour les questions suivantes
  sources: [],        // sources du dernier message agent (pour les liens [n])
};

/* ── Statut du cerveau ──────────────────────────────────────────────── */
fetch("/api/status")
  .then((r) => r.json())
  .then((s) => {
    document.getElementById("brand-name").textContent = s.name || "Atlas";
    statusEl.textContent = `${s.brain} · ${s.search}`;
    statusEl.classList.add("ok");
  })
  .catch(() => {
    statusEl.textContent = "serveur introuvable";
    statusEl.classList.add("bad");
  });

/* ── Petit rendu Markdown (titres, listes, gras, liens, sources [n]) ── */
function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");
}

function inline(text) {
  let t = esc(text);
  t = t.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Gras d'abord, y compris avec des astérisques imbriqués : **Texte (*mot*)**
  t = t.replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>");
  t = t.replace(/(^|[^*])\*([^*\n]+?)\*/g, "$1<em>$2</em>");
  t = t.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Références [1] ou [2, 5] -> liens vers les sources correspondantes
  t = t.replace(/\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]/g, (m, list) => {
    const nums = list.split(",").map((s) => s.trim());
    const links = nums.map((n) => {
      const src = state.sources[Number(n) - 1];
      return src
        ? `<a class="ref" href="${esc(src.url)}" target="_blank" rel="noopener" title="${esc(src.title)}">${n}</a>`
        : null;
    });
    return links.every(Boolean) ? links.join(", ") : m;
  });
  return t;
}

function renderMarkdown(src) {
  const lines = src.replace(/\r/g, "").split("\n");
  let html = "", list = null, para = [], code = false;

  const flushPara = () => {
    if (para.length) { html += `<p>${inline(para.join(" "))}</p>`; para = []; }
  };
  const closeList = () => {
    if (list) { html += `</${list}>`; list = null; }
  };
  const openList = (tag) => {
    flushPara();
    if (list !== tag) { closeList(); html += `<${tag}>`; list = tag; }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.trim().startsWith("```")) {
      flushPara(); closeList();
      html += code ? "</code></pre>" : "<pre><code>";
      code = !code;
      continue;
    }
    if (code) { html += esc(raw) + "\n"; continue; }
    if (!line.trim()) { flushPara(); closeList(); continue; }

    let m;
    if ((m = line.match(/^#{1,2}\s+(.*)$/))) {
      flushPara(); closeList(); html += `<h2>${inline(m[1])}</h2>`;
    } else if ((m = line.match(/^###\s+(.*)$/))) {
      flushPara(); closeList(); html += `<h3>${inline(m[1])}</h3>`;
    } else if ((m = line.match(/^\s*[-*•]\s+(.*)$/))) {
      openList("ul"); html += `<li>${inline(m[1])}</li>`;
    } else if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      openList("ol"); html += `<li>${inline(m[1])}</li>`;
    } else if ((m = line.match(/^>\s?(.*)$/))) {
      flushPara(); closeList(); html += `<blockquote>${inline(m[1])}</blockquote>`;
    } else {
      closeList(); para.push(line.trim());
    }
  }
  if (code) html += "</code></pre>";
  flushPara(); closeList();
  return html;
}

/* ── Construction d'un message ──────────────────────────────────────── */
function addMessage(role) {
  empty.style.display = "none";
  const msg = document.createElement("div");
  msg.className = `msg ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  msg.appendChild(bubble);
  chat.appendChild(msg);
  chat.scrollTop = chat.scrollHeight;
  return bubble;
}

function scrollDown() { chat.scrollTop = chat.scrollHeight; }

function agentShell(bubble) {
  // Affichage type ChatGPT : un seul indicateur pendant la recherche, puis
  // uniquement le texte de la réponse — pas d'étapes, ni de puces de sources,
  // ni de ligne « compris », ni de résumé technique.
  const thinking = document.createElement("div");
  thinking.className = "thinking";
  thinking.textContent = "🔎 Atlas cherche…";
  const answer = document.createElement("div");
  answer.className = "answer";
  bubble.append(thinking, answer);
  return { thinking, answer };
}

/* ── Envoi d'une question (flux NDJSON) ─────────────────────────────── */
async function ask(question) {
  if (state.busy || !question.trim()) return;
  state.busy = true;
  setButton(true);

  const bubble = addMessage("user");
  bubble.textContent = question;
  const reply = addMessage("agent");
  const shell = agentShell(reply);
  const answerBox = shell.answer;
  const cursor = document.createElement("span");
  cursor.className = "cursor";

  let text = "";
  const started = performance.now();
  state.controller = new AbortController();

  try {
    const resp = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: question,
        history: state.history.slice(-6),
      }),
      signal: state.controller.signal,
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `Erreur HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (line) handleEvent(JSON.parse(line));
      }
    }

    function handleEvent(ev) {
      if (ev.type === "step" || ev.type === "understood") {
        return;  // détails techniques masqués (affichage style ChatGPT)
      }
      if (ev.type === "restart") {
        // Le serveur reprend après un flux coupé : on efface la réponse partielle.
        text = "";
        answerBox.innerHTML = "";
        answerBox.appendChild(cursor);
        shell.thinking.hidden = false;
        scrollDown();
      }
      else if (ev.type === "sources") {
        state.sources = ev.items;  // gardées en mémoire, plus affichées
      }
      else if (ev.type === "token") {
        if (!shell.thinking.hidden) shell.thinking.hidden = true;
        text += ev.text;
        answerBox.innerHTML = renderMarkdown(text);
        answerBox.appendChild(cursor);
        scrollDown();
      } else if (ev.type === "done") {
        shell.thinking.hidden = true;
        cursor.remove();
        state.history.push({ role: "user", content: question });
        state.history.push({ role: "assistant", content: text });
        state.history = state.history.slice(-8);
      } else if (ev.type === "error") {
        shell.thinking.hidden = true;
        cursor.remove();
        const box = document.createElement("div");
        box.className = "err";
        box.textContent = "⚠ " + ev.message;
        answerBox.appendChild(box);
        state.history.push({ role: "user", content: question });
      }
    }
  } catch (err) {
    cursor.remove();
    if (err.name === "AbortError") {
      const box = document.createElement("div");
      box.className = "meta";
      box.textContent = text ? "⏹ recherche interrompue" : "⏹ recherche annulée";
      answerBox.appendChild(box);
    } else {
      const box = document.createElement("div");
      box.className = "err";
      box.textContent = "⚠ " + err.message;
      answerBox.appendChild(box);
    }
  } finally {
    shell.thinking.hidden = true;
    state.busy = false;
    state.controller = null;
    setButton(false);
    scrollDown();
  }
}

function setButton(busy) {
  sendBtn.textContent = busy ? "Arrêter" : "Envoyer";
  sendBtn.classList.toggle("stop", busy);
}

/* ── Événements UI ──────────────────────────────────────────────────── */
form.addEventListener("submit", (e) => {
  e.preventDefault();
  if (state.busy) { state.controller?.abort(); return; }
  const q = input.value.trim();
  if (!q) return;
  input.value = "";
  autoSize();
  ask(q);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

function autoSize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
}
input.addEventListener("input", autoSize);

document.querySelectorAll(".chip").forEach((chip) =>
  chip.addEventListener("click", () => ask(chip.textContent.trim()))
);
