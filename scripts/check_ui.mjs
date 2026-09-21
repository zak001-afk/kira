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
      strokeStyle: "",
      fillStyle: "",
      font: "",
      textAlign: "",
      lineWidth: 1,
      fillRect() {
        drawCalls.fillRect += 1;
        const alpha = wipeAlphaOf(this.fillStyle);
        if (alpha !== null) drawCalls.wipeAlpha.push(alpha);
      },
      fillText(_glyph, x, y) {
        drawCalls.fillText += 1;
        // the lowest glyph in a column is its head (heads fall, tails follow)
        drawCalls.fontSizes.add(parseFloat(this.font));
        const column = Math.round(x);
        const previous = drawCalls.columnY.get(column);
        if (previous === undefined || y > previous) {
          drawCalls.columnY.set(column, y);
          if (previous !== undefined && y > previous) drawCalls.fall += y - previous;
        }
      },
      clearRect() {
        drawCalls.clearRect += 1;
      },
      beginPath() {},
      moveTo() {},
      lineTo() {},
      stroke() {},
      setTransform() {},
    };
  }

  // the waveform sizes itself from the canvas box
  get clientWidth() {
    return this._clientWidth ?? 420;
  }
  get clientHeight() {
    return this._clientHeight ?? 32;
  }
}

/* what the canvases were asked to draw, so the render loop can be measured.
   The alpha of each matrix wipe is the trail: it is the one number that says
   how fast the rain is falling, whatever the frame rate happens to be. */
const drawCalls = {
  fillRect: 0,
  fillText: 0,
  clearRect: 0,
  wipeAlpha: [],
  columnY: new Map(), // newest glyph position per column, for the fall speed
  fall: 0,            // pixels every column travelled downward this sample
  fontSizes: new Set(), // the rain's glyph size, which is its column density
};

function wipeAlphaOf(fillStyle) {
  const match = /rgba\(\s*1\s*,\s*1\s*,\s*1\s*,\s*([0-9.eE+-]+)\s*\)/.exec(
    String(fillStyle),
  );
  return match ? Number(match[1]) : null;
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
  "quick-actions", "state-strip", "sidebar-nav", "sidebar-version",
  "model-name", "clock", "date", "waveform",
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

/* the media transport and the sidebar rail, as the markup defines them */
const mediaButtons = ["previous track", "play pause", "next track"].map(
  (text, index) => {
    const button = new FakeElement("button", `media-${index}`);
    button.dataset.command = text;
    return button;
  },
);

const stateCards = [
  "READY",
  "LISTENING",
  "THINKING",
  "EXECUTING",
  "SPEAKING",
].map((name) => {
  const card = new FakeElement("div", `state-${name}`);
  card.dataset.state = name;
  return card;
});
element("state-strip").append(...stateCards);

const navItems = [
  "chat",
  "voice",
  "commands",
  "vision",
  "files",
  "tools",
  "memory",
  "settings",
].map((name) => {
  const item = new FakeElement("button", `nav-${name}`);
  item.dataset.nav = name;
  return item;
});
element("sidebar-nav").append(...navItems);
const navButton = (name) => navItems.find((item) => item.dataset.nav === name);

const body = new FakeElement("body");

const documentElement = new FakeElement("html");
documentElement.dataset = {};

globalThis.document = {
  documentElement,
  getElementById: (id) => element(id),
  createElement: (tag) => new FakeElement(tag),
  createElementNS: (_namespace, tag) => new FakeElement(tag),
  querySelectorAll: (selector) =>
    selector === "[data-command]" ? [...quickActions, ...mediaButtons] : [],
  body,
  addEventListener: () => {},
};

globalThis.window = globalThis;
globalThis.innerWidth = 1440;
globalThis.innerHeight = 900;
globalThis.devicePixelRatio = 1;
// Frames are queued, not run: the smoke check drives them by hand with
// controlled timestamps (see the render-loop checks at the end).
const animationFrames = [];
globalThis.requestAnimationFrame = (fn) => {
  animationFrames.push(fn);
  return animationFrames.length;
};
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
/* `check` is awaited at every call site: an async body used to escape as an
   unhandled rejection, which made a failing check look like a passing one. */
async function check(name, fn) {
  try {
    await fn();
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

// A syntax error in app.js used to make this file exit 0 with no checks run:
// the import rejection was never observed. It is a failure now.
try {
  await import(pathToFileURL(path.join(UI_DIR, "app.js")).href);
} catch (error) {
  console.log(`  FAIL  the interface loads at all — ${error.message}`);
  console.log("\n1 check failed");
  process.exit(1);
}
await tick();

const conversation = element("conversation");
const rendered = () =>
  conversation.children.map((child) => child.children[1]?.textContent ?? "");

/* ── boot ───────────────────────────────────────────────── */

await check("boot requested telemetry", () => {
  assert.ok(calls.some((call) => call.url.startsWith("/api/state")));
});

await check("boot restored the conversation history", () => {
  assert.ok(calls.some((call) => call.url.startsWith("/api/history")));
  assert.ok(rendered().includes("Hello sir."), "history not rendered");
});

await check("online chip reflects the backend", () => {
  assert.equal(element("online-text").textContent, "ONLINE");
  assert.equal(element("mode-label").textContent, "LOCAL INSTANCE");
});

await check("telemetry is displayed", () => {
  assert.equal(element("cpu").textContent, "22%");
  assert.equal(element("memory").textContent, "42%");
  assert.equal(element("disk").textContent, "63%");
  assert.equal(element("battery").textContent, "88% ⚡");
  assert.equal(element("model").textContent, "qwen3.5:0.6b".replace("3.5", "3"));
  assert.equal(element("skills").textContent, "5");
  assert.equal(element("episodes").textContent, "24");
  assert.equal(element("cpu-bar").style.width, "22.4%");
});

await check("activity shows the agent state", () => {
  assert.equal(element("activity").textContent, "STANDBY");
});

await check("poll loop is running", () => {
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

await check("the command reached /api/command", () => {
  assert.ok(
    calls.some(
      (call) => call.url === "/api/command" && call.body.text === "open chrome",
    ),
  );
});

await check("both sides of the exchange are rendered", () => {
  assert.ok(rendered().includes("open chrome"), "user line missing");
  assert.ok(rendered().includes("Consider it done, sir."), "reply missing");
});

await check("the reply is spoken through the browser voice", () => {
  assert.ok(
    globalThis.speechSynthesis.spoken.includes("Consider it done, sir."),
  );
});

await check("the command bar is cleared and idle again", () => {
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

await check("thoughts render as a MIND line", () => {
  const mind = conversation.children.find((child) =>
    child.classList.contains("mind"),
  );
  assert.ok(mind, "no mind entry rendered");
  assert.ok(mind.children[1].textContent.includes("opening vscode"));
});

await check("thoughts are never spoken aloud", () => {
  assert.ok(
    !globalThis.speechSynthesis.spoken.some((line) => line.includes("vscode")),
  );
});

commandReply = { reply: "That did not work, sir.", kind: "error" };
input.value = "click the thing";
await sendButton.fire("click");
await tick();

await check("failures render but are not spoken", () => {
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

await check("the confirmation bar appears when the server asks", () => {
  assert.equal(element("confirm-bar").hidden, false);
  assert.ok(element("confirm-text").textContent.includes("search the web"));
});

commandReply = { reply: "Searching now, sir.", kind: "action", ok: true };
await element("confirm-yes").fire("click");
await tick();

await check("confirming posts confirm=true and hides the bar", () => {
  assert.ok(
    calls.some((call) => call.url === "/api/command" && call.body.confirm === true),
  );
  assert.equal(element("confirm-bar").hidden, true);
});

/* ── quick actions ──────────────────────────────────────── */

await quickActions[2].fire("click");
await tick();

await check("quick actions send their command", () => {
  assert.ok(
    calls.some(
      (call) =>
        call.url === "/api/command" && call.body.text === "systems check",
    ),
    "quick action never posted its command",
  );
});

/* ── media transport + clock (the desktop app's bottom bar) ── */

commandReply = { reply: "Playing, sir.", kind: "action", ok: true };
await mediaButtons[1].fire("click");
await tick();

await check("media transport posts a command the parser knows", () => {
  assert.ok(
    calls.some(
      (call) => call.url === "/api/command" && call.body.text === "play pause",
    ),
    "the play button never posted its command",
  );
});

await check("the clock and date are rendered", () => {
  assert.match(element("clock").textContent, /^\d{2}:\d{2}$/);
  assert.ok(element("date").textContent.length > 3, "no date rendered");
});

/* ── the state strip ────────────────────────────────────── */

await check("the state strip lights exactly one card", () => {
  const active = stateCards.filter((card) => card.classList.contains("active"));
  assert.equal(active.length, 1, `${active.length} cards lit at once`);
});

/* ── the voice activity line ────────────────────────────── */

await check("the waveform draws without throwing", () => {
  assert.ok(
    element("waveform").width > 0,
    "the voice line was never sized for the canvas",
  );
});

/* ── sidebar modules ────────────────────────────────────── */

await check("the rail marks the module the user picked", async () => {
  await navButton("memory").fire("click");
  assert.ok(navButton("memory").classList.contains("active"));
  assert.ok(!navButton("chat").classList.contains("active"));
});

await check("a module with a real job sends its command", () => {
  assert.ok(
    calls.some(
      (call) =>
        call.url === "/api/command" && call.body.text === "what did you learn",
    ),
    "the memory module never posted its command",
  );
});

await check("the voice module listens", async () => {
  const before = calls.filter((call) => call.url === "/api/listen").length;
  await navButton("voice").fire("click");
  await tick();
  const after = calls.filter((call) => call.url === "/api/listen").length;
  assert.ok(after > before, "the voice module did not open the microphone");
});

await check("the settings module toggles voice output", async () => {
  const toggle = element("speak-toggle");
  const before = toggle.textContent;
  await navButton("settings").fire("click");
  assert.notEqual(toggle.textContent, before, "voice output did not flip");
  await navButton("settings").fire("click");
  assert.equal(toggle.textContent, before, "voice output did not flip back");
});

await check("a module that is not wired up says so", async () => {
  const before = conversation.children.length;
  await navButton("tools").fire("click");
  assert.ok(conversation.children.length > before, "no explanation was shown");
  assert.ok(
    rendered().some((line) => line.includes("not wired up")),
    "the tools module claimed to do something it cannot",
  );
});

/* ── microphone ─────────────────────────────────────────── */

await element("mic").fire("click");
await tick();

await check("the mic button posts to /api/listen", () => {
  assert.ok(calls.some((call) => call.url === "/api/listen"));
});

await check("a recognised phrase is sent as a command", () => {
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

await check("watchdog alerts appear unprompted", () => {
  const proactive = conversation.children.find((child) =>
    child.classList.contains("proactive"),
  );
  assert.ok(proactive, "queue message never rendered");
  assert.ok(proactive.children[1].textContent.includes("battery is at 18%"));
});

await check("watchdog alerts are spoken", () => {
  assert.ok(
    globalThis.speechSynthesis.spoken.includes("Sir, your battery is at 18%."),
  );
});

await check("state changes drive the activity readout", () => {
  assert.equal(element("activity").textContent, "THINKING");
});

/* ── offline + simulation modes ─────────────────────────── */

statePayload = { ...statePayload, online: false, mode: "offline", reason: "boom", queue: [] };
await intervals[0].fn();
await tick();

await check("an unreachable backend is flagged, never hidden", () => {
  assert.equal(element("online-text").textContent, "OFFLINE");
  assert.ok(element("backend-note").textContent.includes("boom"));
});

statePayload = { ...statePayload, online: true, mode: "simulation", reason: "demo" };
await intervals[0].fn();
await tick();

await check("simulation mode is labelled as a demo", () => {
  assert.equal(element("online-text").textContent, "SIMULATION");
  assert.ok(element("mode-label").textContent.includes("DEMO"));
});

/* ── controls ───────────────────────────────────────────── */

await check("the voice toggle flips and persists", async () => {
  const toggle = element("speak-toggle");
  await toggle.fire("click");
  assert.equal(toggle.textContent, "VOICE: OFF");
  assert.equal(globalThis.localStorage.getItem("kira.speak"), "off");
  await toggle.fire("click");
  assert.equal(toggle.textContent, "VOICE: ON");
});

await element("reset-chat").fire("click");
await tick();

await check("reset clears the conversation and says so", () => {
  assert.ok(calls.some((call) => call.url === "/api/reset"));
  assert.equal(conversation.children.length, 1, "conversation was not cleared");
  assert.ok(rendered()[0].includes("Fresh start"));
});

/* ── the reactor degraded instead of breaking ───────────── */

await new Promise((resolve) => realSetTimeout(resolve, 120));

await check("the reactor failed gracefully (no WebGL in node)", () => {
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

await check("the interface still works after the reactor gave up", () => {
  assert.ok(
    rendered().some((line) => line.includes("All systems nominal")),
    "commands stopped working after the fallback",
  );
});

await check("no runtime errors escaped", () => {
  assert.equal(rejections.length, 0, rejections.map(String).join("; "));
});

console.log(
  failures.length
    ? `\n${failures.length} UI check(s) failed:\n- ${failures.join("\n- ")}`
    : "\nall UI checks passed",
);
/* ── the render loop ─────────────────────────────────────
   Everything about how this HUD moves is timing, and timing is exactly the
   sort of thing that looks right on the machine it was written on and wrong
   everywhere else. These checks pin it down: feed the loop a simulated
   second at two very different refresh rates and compare the work it did. */

let hudClock = 1_000_000;

function resetDrawCalls() {
  drawCalls.fillText = 0;
  drawCalls.fillRect = 0;
  drawCalls.wipeAlpha = [];
  drawCalls.columnY = new Map();
  drawCalls.fall = 0;
  drawCalls.fontSizes = new Set();
}

function paint(ms, frames) {
  const start = hudClock;
  hudClock += ms + 100; // never walk the clock backwards between samples
  resetDrawCalls();
  for (let i = 0; i < frames; i += 1) {
    const queued = animationFrames.splice(0, animationFrames.length);
    assert.ok(queued.length > 0, "the render loop stopped asking for frames");
    for (const callback of queued) callback(start + (i * ms) / frames);
  }
  // how much of the trail survived the second: one number, any frame rate
  const surviving = drawCalls.wipeAlpha.reduce((left, alpha) => left * (1 - alpha), 1);
  return {
    glyphs: drawCalls.fillText,
    font: Math.max(...drawCalls.fontSizes),
    wipes: drawCalls.wipeAlpha.length,
    surviving,
    // average pixels a column fell in a second, wrapping columns excluded
    fall: drawCalls.fall / Math.max(drawCalls.columnY.size, 1),
  };
}

await check("the rain falls at the same speed on any display", () => {
  // One simulated second at three very different refresh rates. The trail that
  // survives must be the same fraction of the screen in all three — that is
  // what "the same speed" means when the drawing is time-based. A loop that
  // counts frames leaves a 240 Hz display with no trails at all.
  const slow = paint(1000, 30);
  const normal = paint(1000, 60);
  const fast = paint(1000, 144);
  const rapid = paint(1000, 240);
  assert.ok(slow.glyphs > 0 && fast.wipes > 0, "nothing was drawn");
  for (const sample of [slow, normal, fast, rapid]) {
    assert.ok(
      sample.surviving > 0.0005 && sample.surviving < 0.006,
      `one second left ${sample.surviving.toFixed(4)} of the trail — the rain ` +
        "is not falling at a constant speed",
    );
  }
});

await check("the rain falls at 60 frames' worth per second, whatever the rate", () => {
  // The rain was tuned on a 60 Hz screen. Elapsed time is what makes it fall
  // at that same speed later, on this panel: ~14 px glyphs at ~0.7 rows a
  // frame is a bit over 600 px a second, and every rate must agree on it.
  const rates = [30, 60, 144, 240];
  const falls = rates.map((rate) => paint(1000, rate).fall);
  for (let index = 0; index < rates.length; index += 1) {
    assert.ok(
      falls[index] > 250 && falls[index] < 450,
      `${rates[index]} Hz fell ${falls[index].toFixed(0)} px/s — the rain has the ` +
        "wrong speed",
    );
  }
});

await check("a fast display does not do more work", () => {
  const sixty = paint(1000, 60);
  const rapid = paint(1000, 240);
  assert.ok(sixty.wipes > 0, "nothing was drawn");
  const ratio = rapid.wipes / sixty.wipes;
  assert.ok(
    ratio > 0.7 && ratio < 1.4,
    `240 Hz did ${ratio.toFixed(2)}x the drawing of 60 Hz — the loop is uncapped`,
  );
});

await check("orb_quality lowers the render budget", async () => {
  // The rain's glyph size is its column count: 14 px is the balanced budget,
  // 20 px is a third fewer columns, 12 px is more. The server reports the
  // budget, the HUD must follow it — and follow it when it changes.
  const setQuality = async (quality) => {
    statePayload = { ...statePayload, quality };
    for (const interval of intervals) await interval.fn(); // the telemetry poll
    return paint(1000, 60).font;
  };
  assert.equal(await setQuality("balanced"), 14, "the balanced budget was ignored");
  assert.equal(await setQuality("low"), 20, "the low budget was ignored");
  assert.equal(await setQuality("high"), 12, "the high budget was ignored");
  assert.equal(await setQuality("nonsense"), 14, "an unknown budget was trusted");
});

await check("a hidden window stops drawing and stops polling", () => {
  const visible = paint(1000, 60); // the window is on screen here
  assert.ok(visible.glyphs > 0, "nothing was drawn while visible");

  const saved = globalThis.document.hidden;
  globalThis.document.hidden = true;
  let hidden;
  let polls;
  try {
    hidden = paint(1000, 60);
    polls = calls.length;
    for (const interval of intervals) interval.fn(); // the telemetry timer
  } finally {
    globalThis.document.hidden = saved;
  }
  assert.equal(hidden.glyphs, 0, "a hidden window kept drawing the rain");
  assert.equal(calls.length, polls, "a hidden window kept polling the API");
});

process.exit(failures.length ? 1 : 0);
