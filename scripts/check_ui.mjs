/* =========================================================
   KIRA // UI SMOKE CHECK (node, no browser)

   Runs ui/app.js against a minimal DOM + fetch stub and asserts that the
   HUD really works: boot restores history and telemetry, the command bar
   posts to the API and renders KIRA's reply, thoughts render as MIND lines
   and stay silent, errors stay silent, the confirmation bar round-trips,
   quick actions and the mic fire, unprompted watchdog alerts are spoken,
   and the matrix renderer runs without throwing.

   Usage:  node scripts/check_ui.mjs
   Exits 0 on success, 1 on the first failed assertion.
   ========================================================= */

import assert from "node:assert/strict";
import { register } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const UI_DIR = path.resolve(
  path.dirname(new URL(import.meta.url).pathname),
  "..",
  "ui",
);

/* ---------------------------------------------------------
   DOM STUB
   --------------------------------------------------------- */

class FakeClassList {
  constructor() {
    this.set = new Set();
  }
  add(...names) {
    names.forEach((name) => this.set.add(name));
  }
  remove(...names) {
    names.forEach((name) => this.set.delete(name));
  }
  toggle(name, force) {
    const on = force === undefined ? !this.set.has(name) : force;
    if (on) this.set.add(name);
    else this.set.delete(name);
    return on;
  }
  contains(name) {
    return this.set.has(name);
  }
  toString() {
    return [...this.set].join(" ");
  }
}

class FakeElement {
  constructor(tag = "div", id = "") {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.classList = new FakeClassList();
    this.style = {};
    this.dataset = {};
    this.children = [];
    this.hidden = false;
    this.value = "";
    this.disabled = false;
    this.scrollTop = 0;
    this._text = "";
    this._html = "";
    this._handlers = new Map();
  }

  // the real DOM coerces everything assigned to textContent into a string
  set textContent(value) {
    this._text = String(value);
  }
  get textContent() {
    return this._text;
  }

  set innerHTML(value) {
    this._html = String(value);
    if (value === "") this.children = [];
  }
  get innerHTML() {
    return this._html;
  }

  get firstElementChild() {
    return this.children[0] || null;
  }

  get scrollHeight() {
    return this.children.length * 40;
  }

  append(...nodes) {
    nodes.forEach((node) => this.appendChild(node));
  }

  appendChild(node) {
    this.children.push(node);
    return node;
  }

  removeChild(node) {
    this.children = this.children.filter((child) => child !== node);
    return node;
  }

  addEventListener(type, handler) {
    if (!this._handlers.has(type)) this._handlers.set(type, []);
    this._handlers.get(type).push(handler);
  }

  async fire(type) {
    for (const handler of this._handlers.get(type) || []) await handler();
  }

  focus() {}

  getContext(type) {
    if (type !== "2d") return null; // no WebGL here — must degrade, not throw
    return {
      fillStyle: "",
      font: "",
      textAlign: "",
      fillRect() {},
      fillText() {},
    };
  }
}

const elements = new Map();

function element(id) {
  if (!elements.has(id)) elements.set(id, new FakeElement("div", id));
  return elements.get(id);
}

[
  "conversation", "thinking", "thinking-label", "command", "send", "mic",
  "confirm-bar", "confirm-text", "confirm-yes", "confirm-no", "online-chip",
  "online-text", "mode-label", "activity", "activity-row", "cpu", "memory",
  "disk", "battery", "cpu-bar", "memory-bar", "model", "skills", "episodes",
  "backend-note", "matrix", "scene-container", "speak-toggle", "reset-chat",
  "quick-actions",
].forEach(element);

const quickActions = [
  "open chrome",
  "what is on my screen",
  "systems check",
  "what did you learn",
].map((text, index) => {
  const button = new FakeElement("button", `quick-${index}`);
  button.dataset.command = text;
  return button;
});

const body = new FakeElement("body");

globalThis.document = {
  getElementById: (id) => element(id),
  createElement: (tag) => new FakeElement(tag),
  createElementNS: (_namespace, tag) => new FakeElement(tag),
  querySelectorAll: (selector) =>
    selector === "#quick-actions button" ? quickActions : [],
  body,
  addEventListener: () => {},
};

globalThis.window = globalThis;
globalThis.innerWidth = 1440;
globalThis.innerHeight = 900;
globalThis.devicePixelRatio = 1;
globalThis.requestAnimationFrame = () => 0; // render loops run once, no spin
globalThis.addEventListener = () => {};
globalThis.localStorage = {
  store: new Map(),
  getItem(key) {
    return this.store.has(key) ? this.store.get(key) : null;
  },
  setItem(key, value) {
    this.store.set(key, String(value));
  },
};
globalThis.speechSynthesis = {
  spoken: [],
  cancel() {
    this.cancelled = (this.cancelled || 0) + 1;
  },
  speak(utterance) {
    this.spoken.push(utterance.text);
  },
  getVoices: () => [{ name: "Microsoft Aria Online (Natural)", lang: "en-US" }],
};
globalThis.SpeechSynthesisUtterance = class {
  constructor(text) {
    this.text = text;
  }
};

// capture the poll timer so the smoke check can tick it by hand
const intervals = [];
const realSetTimeout = globalThis.setTimeout;
globalThis.setInterval = (fn, ms) => {
  intervals.push({ fn, ms });
  return intervals.length;
};
globalThis.setTimeout = (fn) => {
  fn();
  return 1;
};

// keep an eye on what the app logs
const logged = [];
const realConsoleInfo = console.info;
console.info = (...args) => {
  logged.push(args.join(" "));
  realConsoleInfo(...args);
};

/* ---------------------------------------------------------
   FETCH STUB
   --------------------------------------------------------- */

const calls = [];
let statePayload = {
  online: true,
  mode: "live",
  state: "READY",
  cpu: 22.4,
  memory: 41.7,
  disk: 63.2,
  battery: { percent: 88, plugged: true },
  model: "qwen3:0.6b",
  skills: 5,
  episodes: 24,
  queue: [],
};
let commandReply = {
  reply: "Consider it done, sir.",
  kind: "action",
  action: "open_app",
  ok: true,
};
let listenPayload = { text: "systems check" };

const jsonResponse = (payload) => ({
  ok: true,
  status: 200,
  statusText: "OK",
  json: async () => payload,
});

globalThis.fetch = async (url, options = {}) => {
  const body = options.body ? JSON.parse(options.body) : {};
  calls.push({ url, body });

  if (url.startsWith("/api/history")) {
    return jsonResponse({
      messages: [{ role: "kira", text: "Hello sir.", kind: "message" }],
    });
  }
  if (url.startsWith("/api/state")) return jsonResponse(statePayload);
  if (url.startsWith("/api/command")) return jsonResponse(commandReply);
  if (url.startsWith("/api/listen")) return jsonResponse(listenPayload);
  if (url.startsWith("/api/reset")) return jsonResponse({ ok: true });
  return { ok: false, status: 404, statusText: "Not Found" };
};

/* ---------------------------------------------------------
   HARNESS
   --------------------------------------------------------- */

const rejections = [];
process.on("unhandledRejection", (error) => rejections.push(error));
process.on("uncaughtException", (error) => rejections.push(error));

const failures = [];
function check(name, fn) {
  try {
    fn();
    console.log(`  ok    ${name}`);
  } catch (error) {
    failures.push(`${name}: ${error.message}`);
    console.log(`  FAIL  ${name} — ${error.message}`);
  }
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

console.log("KIRA UI smoke check");

// Node cannot read the browser import map, so map the same specifiers by hand.
// This makes the run exercise the *real vendored* Three.js build.
register(new URL("./three-resolver.mjs", import.meta.url));

/* ── the vendored reactor library ───────────────────────── */

try {
  const THREE = await import("three");
  const { EffectComposer } = await import("three/addons/postprocessing/EffectComposer.js");
  const { RenderPass } = await import("three/addons/postprocessing/RenderPass.js");
  const { UnrealBloomPass } = await import("three/addons/postprocessing/UnrealBloomPass.js");
  check("the vendored Three.js build loads offline", () => {
    assert.equal(typeof THREE.WebGLRenderer, "function");
    assert.equal(typeof THREE.Scene, "function");
    assert.ok(THREE.REVISION, "no revision reported");
    assert.equal(typeof EffectComposer, "function");
    assert.equal(typeof RenderPass, "function");
    assert.equal(typeof UnrealBloomPass, "function");
  });
} catch (error) {
  check("the vendored Three.js build loads offline", () => {
    throw error;
  });
}

await import(pathToFileURL(path.join(UI_DIR, "app.js")).href);
await tick();

const conversation = element("conversation");
const rendered = () =>
  conversation.children.map((child) => child.children[1]?.textContent ?? "");

/* ── boot ───────────────────────────────────────────────── */

check("boot requested telemetry", () => {
  assert.ok(calls.some((call) => call.url.startsWith("/api/state")));
});

check("boot restored the conversation history", () => {
  assert.ok(calls.some((call) => call.url.startsWith("/api/history")));
  assert.ok(rendered().includes("Hello sir."), "history not rendered");
});

check("online chip reflects the backend", () => {
  assert.equal(element("online-text").textContent, "ONLINE");
  assert.equal(element("mode-label").textContent, "LOCAL INSTANCE");
});

check("telemetry is displayed", () => {
  assert.equal(element("cpu").textContent, "22%");
  assert.equal(element("memory").textContent, "42%");
  assert.equal(element("disk").textContent, "63%");
  assert.equal(element("battery").textContent, "88% ⚡");
  assert.equal(element("model").textContent, "qwen3.5:0.6b".replace("3.5", "3"));
  assert.equal(element("skills").textContent, "5");
  assert.equal(element("episodes").textContent, "24");
  assert.equal(element("cpu-bar").style.width, "22.4%");
});

check("activity shows the agent state", () => {
  assert.equal(element("activity").textContent, "STANDBY");
});

check("poll loop is running", () => {
  assert.ok(intervals.length >= 1, "no interval registered");
  assert.ok(
    intervals.some((timer) => timer.ms <= 5000),
    "telemetry is not polled",
  );
});

/* ── sending a command ──────────────────────────────────── */

const input = element("command");
const sendButton = element("send");

input.value = "open chrome";
await sendButton.fire("click");
await tick();

check("the command reached /api/command", () => {
  assert.ok(
    calls.some(
      (call) => call.url === "/api/command" && call.body.text === "open chrome",
    ),
  );
});

check("both sides of the exchange are rendered", () => {
  assert.ok(rendered().includes("open chrome"), "user line missing");
  assert.ok(rendered().includes("Consider it done, sir."), "reply missing");
});

check("the reply is spoken through the browser voice", () => {
  assert.ok(
    globalThis.speechSynthesis.spoken.includes("Consider it done, sir."),
  );
});

check("the command bar is cleared and idle again", () => {
  assert.equal(input.value, "");
  assert.equal(sendButton.disabled, false);
});

/* ── inner monologue, failures ──────────────────────────── */

commandReply = {
  reply: "I opened the editor, sir.",
  thought: "The user wants the code editor; opening vscode.",
  kind: "action",
  ok: true,
};
input.value = "open my editor";
await sendButton.fire("click");
await tick();

check("thoughts render as a MIND line", () => {
  const mind = conversation.children.find((child) =>
    child.classList.contains("mind"),
  );
  assert.ok(mind, "no mind entry rendered");
  assert.ok(mind.children[1].textContent.includes("opening vscode"));
});

check("thoughts are never spoken aloud", () => {
  assert.ok(
    !globalThis.speechSynthesis.spoken.some((line) => line.includes("vscode")),
  );
});

commandReply = { reply: "That did not work, sir.", kind: "error" };
input.value = "click the thing";
await sendButton.fire("click");
await tick();

check("failures render but are not spoken", () => {
  const failed = conversation.children.find((child) =>
    child.classList.contains("failed"),
  );
  assert.ok(failed, "no failure entry rendered");
  assert.ok(!globalThis.speechSynthesis.spoken.includes("That did not work, sir."));
});

/* ── confirmation flow ──────────────────────────────────── */

commandReply = {
  reply: "search the web for kira",
  kind: "confirm",
  needs_confirmation: true,
  action_name: "search",
};
input.value = "search for kira";
await sendButton.fire("click");
await tick();

check("the confirmation bar appears when the server asks", () => {
  assert.equal(element("confirm-bar").hidden, false);
  assert.ok(element("confirm-text").textContent.includes("search the web"));
});

commandReply = { reply: "Searching now, sir.", kind: "action", ok: true };
await element("confirm-yes").fire("click");
await tick();

check("confirming posts confirm=true and hides the bar", () => {
  assert.ok(
    calls.some((call) => call.url === "/api/command" && call.body.confirm === true),
  );
  assert.equal(element("confirm-bar").hidden, true);
});

/* ── quick actions ──────────────────────────────────────── */

await quickActions[2].fire("click");
await tick();

check("quick actions send their command", () => {
  assert.ok(
    calls.some(
      (call) =>
        call.url === "/api/command" && call.body.text === "systems check",
    ),
    "quick action never posted its command",
  );
});

/* ── microphone ─────────────────────────────────────────── */

await element("mic").fire("click");
await tick();

check("the mic button posts to /api/listen", () => {
  assert.ok(calls.some((call) => call.url === "/api/listen"));
});

check("a recognised phrase is sent as a command", () => {
  assert.ok(
    calls.some(
      (call) => call.url === "/api/command" && call.body.text === "systems check",
    ),
  );
});

/* ── unprompted alerts (watchdog queue) ─────────────────── */

statePayload = {
  ...statePayload,
  state: "THINKING",
  queue: ["Sir, your battery is at 18%."],
};
await intervals[0].fn();
await tick();

check("watchdog alerts appear unprompted", () => {
  const proactive = conversation.children.find((child) =>
    child.classList.contains("proactive"),
  );
  assert.ok(proactive, "queue message never rendered");
  assert.ok(proactive.children[1].textContent.includes("battery is at 18%"));
});

check("watchdog alerts are spoken", () => {
  assert.ok(
    globalThis.speechSynthesis.spoken.includes("Sir, your battery is at 18%."),
  );
});

check("state changes drive the activity readout", () => {
  assert.equal(element("activity").textContent, "THINKING");
});

/* ── offline + simulation modes ─────────────────────────── */

statePayload = { ...statePayload, online: false, mode: "offline", reason: "boom", queue: [] };
await intervals[0].fn();
await tick();

check("an unreachable backend is flagged, never hidden", () => {
  assert.equal(element("online-text").textContent, "OFFLINE");
  assert.ok(element("backend-note").textContent.includes("boom"));
});

statePayload = { ...statePayload, online: true, mode: "simulation", reason: "demo" };
await intervals[0].fn();
await tick();

check("simulation mode is labelled as a demo", () => {
  assert.equal(element("online-text").textContent, "SIMULATION");
  assert.ok(element("mode-label").textContent.includes("DEMO"));
});

/* ── controls ───────────────────────────────────────────── */

check("the voice toggle flips and persists", async () => {
  const toggle = element("speak-toggle");
  await toggle.fire("click");
  assert.equal(toggle.textContent, "VOICE: OFF");
  assert.equal(globalThis.localStorage.getItem("kira.speak"), "off");
  await toggle.fire("click");
  assert.equal(toggle.textContent, "VOICE: ON");
});

await element("reset-chat").fire("click");
await tick();

check("reset clears the conversation and says so", () => {
  assert.ok(calls.some((call) => call.url === "/api/reset"));
  assert.equal(conversation.children.length, 1, "conversation was not cleared");
  assert.ok(rendered()[0].includes("Fresh start"));
});

/* ── the reactor degraded instead of breaking ───────────── */

await new Promise((resolve) => realSetTimeout(resolve, 120));

check("the reactor failed gracefully (no WebGL in node)", () => {
  assert.ok(
    body.classList.contains("no-webgl"),
    "the CSS fallback never engaged — a WebGL failure would leave a dead screen",
  );
  assert.ok(
    logged.some((line) => line.includes("3D reactor unavailable")),
    "the degradation was not logged",
  );
});

commandReply = { reply: "All systems nominal, sir.", kind: "action", ok: true };
input.value = "systems check";
await sendButton.fire("click");
await tick();

check("the interface still works after the reactor gave up", () => {
  assert.ok(
    rendered().some((line) => line.includes("All systems nominal")),
    "commands stopped working after the fallback",
  );
});

check("no runtime errors escaped", () => {
  assert.equal(rejections.length, 0, rejections.map(String).join("; "));
});

console.log(
  failures.length
    ? `\n${failures.length} UI check(s) failed:\n- ${failures.join("\n- ")}`
    : "\nall UI checks passed",
);
process.exit(failures.length ? 1 : 0);
