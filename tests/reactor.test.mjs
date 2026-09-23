import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";
import { SpeechPlayer } from "../ui/speech.mjs";
import { Hologram, projectionFrame, waveformPath } from "../ui/hologram.mjs";
import { playerRig } from "./support/speech-fakes.mjs";

// Run the actual cockpit controller with DOM/audio doubles. Rendering now uses
// local SVG/CSS, not a WebGL shader; keep testing speech -> visible field wiring.
function appRig(options = {}) {
  const rig = playerRig(options);
  const elements = new Map(), listeners = new Map(), requests = [];
  const storage = new Map(options.motionPreference ? [["kira.motion", options.motionPreference]] : []);
  class Element {
    constructor(id) {
      this.id = id;
      this.children = [];
      this.dataset = {};
      this.attributes = {};
      this.events = new Map();
      this.hidden = false;
      this.value = "";
      this._text = "";
      this.innerHTML = "";
      this.style = { setProperty(key, value) { this[key] = value; } };
      const classes = new Set();
      this.classList = {
        add: (...names) => names.forEach(n => classes.add(n)),
        remove: (...names) => names.forEach(n => classes.delete(n)),
        contains: n => classes.has(n),
        toggle(n, force) { const on = force ?? !classes.has(n); if (on) classes.add(n); else classes.delete(n); return on; },
      };
    }
    set textContent(text) { this._text = String(text); this.children = []; }
    get textContent() { return this._text + this.children.map(c => c.textContent).join(""); }
    get firstElementChild() { return this.children[0]; }
    appendChild(child) { this.children.push(child); child.parent = this; return child; }
    append(...children) { children.forEach(child => this.appendChild(child)); }
    replaceChildren(...children) { this.children = []; this._text = ""; this.append(...children); }
    remove() { if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this); }
    setAttribute(key, value) { this.attributes[key] = value; }
    getAttribute(key) { return this.attributes[key]; }
    addEventListener(name, callback) { this.events.set(name, callback); }
    click() { return this.events.get("click")?.({ target: this }); }
    querySelector(selector) { return element(`${this.id}/${selector}`); }
    focus() {} scrollIntoView() {}
    close() { this.open = false; }
    showModal() { this.open = true; }
  }
  function element(id) {
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  }
  let serial = 0;
  const mediaQuery = { matches: Boolean(options.reducedMotion), addEventListener() {}, removeEventListener() {} };
  const document = {
    hidden: false,
    documentElement: element("html"),
    getElementById: element,
    createElement: () => element(`new-${++serial}`),
    querySelector: element,
    querySelectorAll: () => [],
    addEventListener(name, callback) { listeners.set(`document:${name}`, callback); },
  };
  const context = vm.createContext({
    ...rig.env, Hologram,
    SpeechPlayer: class extends SpeechPlayer {
      constructor(options) { super({ ...options, env: rig.env }); }
    },
    console: { log() {}, error() {} }, document,
    navigator: { language: "fr-FR" },
    location: { protocol: "https:", hostname: "8766-example.e2b.app" },
    matchMedia: () => mediaQuery,
    localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    requestAnimationFrame() { return 1; }, cancelAnimationFrame() {},
    setInterval() {}, clearInterval() {},
    addEventListener(name, callback) { listeners.set(name, callback); },
    fetch: async (url, init) => {
      requests.push({ url, init });
      const data = options.response ? await options.response(url, init)
        : url === "/api/tts" ? { audio: "YWJj" }
        : url === "/api/command" ? { response: "Hello there, Operator." }
        : url === "/api/status" ? { model: "qwen3:0.6b", backend_available: true }
        : url === "/api/system" ? { cpu_percent: 12, memory_percent: 24, disk_percent: 30, gpu: "N/A" }
        : url.includes("/api/tasks") ? { tasks: [] } : {};
      return { ok: !data.error, status: data.error ? 503 : 200, json: async () => data };
    },
  });
  context.window = context;
  const source = readFileSync(new URL("../ui/app.js", import.meta.url), "utf8").replace(/^import .*;\n/gm, "");
  vm.runInContext(source + `\nglobalThis.probe = {
    speech, speak, stopSpeaking, sendCommand, setActivity, animate,
    hologram, motionDisabled, addMessage, updateTelemetry, updateStatus, openPanel,
  };`, context);
  return {
    ...rig, probe: context.probe, element, listeners, requests, storage, document,
    step(ms = 100) { rig.advance(ms); context.probe.animate(); },
  };
}
const flush = () => new Promise(setImmediate);

test("the holographic field expands with speech and returns to its idle size", async () => {
  const rig = appRig();
  const before = rig.probe.hologram.frame.haloY;
  await rig.probe.speak("Hello there, Operator.");
  rig.step();
  assert.ok(rig.probe.hologram.frame.haloY > before + 0.03, "speech never reached the rendered field");
  assert.ok(rig.probe.hologram.frame.energy > 0);
  assert.notEqual(rig.element("halo").style.transform, "scale(1.0000, 1.0000)");
  assert.ok(rig.probe.hologram.frame.portraitScale > 1);
  rig.audios[0].onended();
  for (let i = 0; i < 25; i++) rig.step();
  assert.equal(rig.probe.hologram.frame.energy, 0);
  assert.equal(rig.probe.hologram.frame.haloY, 1);
  assert.equal(rig.element("activity").textContent, "READY");
});

test("the command handler's READY cannot overwrite active speech", async () => {
  const rig = appRig();
  await rig.probe.sendCommand("hello");
  await flush();
  assert.equal(rig.audios.length, 1);
  assert.equal(rig.element("activity").textContent, "SPEAKING");
  rig.probe.setActivity("READY");
  assert.equal(rig.element("activity").textContent, "SPEAKING");
});

test("the mute button stops motion, releases audio, and updates all controls", async () => {
  const rig = appRig();
  await rig.probe.speak("hello");
  rig.step();
  rig.element("mute").click();
  assert.equal(rig.probe.speech.enabled, false);
  assert.ok(rig.audios[0].paused);
  assert.equal(rig.revoked.length, 1);
  for (let i = 0; i < 25; i++) rig.step();
  assert.equal(rig.probe.hologram.frame.energy, 0);
  assert.equal(rig.element("deck-voice-state").textContent, "MUTED");
  assert.equal(rig.element("voice-test").disabled, true);
  assert.equal(rig.storage.get("kira.voice"), "off");
});

test("reduced motion removes deformation, displacement, and moving waveforms", async () => {
  const rig = appRig({ reducedMotion: true });
  await rig.probe.speak("hello");
  rig.step();
  assert.equal(rig.probe.hologram.frame.portraitScale, 1);
  assert.equal(rig.probe.hologram.frame.portraitY, 0);
  assert.equal(rig.probe.hologram.frame.energy, 0);
  assert.equal(rig.probe.hologram.frame.time, 0);
  assert.ok(rig.probe.hologram.frame.light <= 0.12);
  assert.equal(rig.element("voice-wave").getAttribute("d"), waveformPath(0, 0));
});

test("bass and treble feed the real composited field and stay bounded", () => {
  const bass = projectionFrame({ energy: 0.5, low: 1, high: 0 });
  const treble = projectionFrame({ energy: 0.5, low: 0, high: 1 });
  assert.ok(bass.haloX > treble.haloX);
  const rig = appRig();
  rig.probe.hologram.update({ energy: 0.5, low: 0, high: 1 });
  const bright = rig.element("halo").style.filter;
  rig.probe.hologram.update({ energy: 0.5, low: 0, high: 0 });
  assert.notEqual(bright, rig.element("halo").style.filter);
  const extreme = projectionFrame({ energy: 900, low: -2, high: Infinity });
  assert.equal(extreme.energy, 1);
  assert.equal(extreme.low, 0);
  assert.ok(extreme.haloY <= 1.1);
  assert.ok(!waveformPath(NaN).includes("NaN"));
});

test("page exit cleans up the app's audio, request timers and pending requests", async () => {
  const rig = appRig();
  await flush();
  await rig.probe.speak("hello");
  rig.listeners.get("pagehide")();
  assert.equal(rig.probe.speech.session, null);
  assert.equal(rig.contexts[0].state, "closed");
  assert.equal(rig.timers.size, 0);
});

test("Motion On explicitly overrides system reduced motion", async () => {
  const rig = appRig({ reducedMotion: true });
  assert.equal(rig.element("motion-toggle").textContent, "MOTION: AUTO");
  assert.match(rig.element("motion-status").textContent, /SYSTEM SETTING/);
  rig.element("motion-toggle").click();
  await rig.probe.speak("hello");
  rig.step();
  assert.equal(rig.element("motion-toggle").textContent, "MOTION: ON");
  assert.equal(rig.document.documentElement.dataset.motion, "on");
  assert.ok(rig.probe.hologram.frame.haloY > 1.03);
  assert.match(rig.element("motion-status").textContent, /AUDIO/);
});

test("Test Motion checks the compositor without audio, network or Ollama", () => {
  const rig = appRig();
  const beforeRequests = rig.requests.length;
  rig.element("motion-test").click();
  rig.step(500);
  assert.ok(rig.probe.hologram.frame.haloY > 1.02);
  assert.equal(rig.audios.length, 0);
  assert.equal(rig.requests.length, beforeRequests);
  assert.match(rig.element("motion-status").textContent, /TEST MOTION/);
  rig.step(4000);
  assert.equal(rig.probe.hologram.frame.haloY, 1);
});

test("Motion Off is respected during the visual test", () => {
  const rig = appRig();
  rig.element("motion-toggle").click(); // on
  rig.element("motion-toggle").click(); // off
  rig.element("motion-test").click();
  rig.step(500);
  assert.equal(rig.probe.hologram.frame.haloY, 1);
  assert.match(rig.element("motion-status").textContent, /MOTION OFF/);
  assert.equal(rig.document.documentElement.dataset.motion, "off");
});

test("Test Voice exercises speech without sending a desktop command", async () => {
  const rig = appRig();
  rig.element("voice-test").click();
  await flush();
  rig.step();
  assert.equal(rig.audios.length, 1);
  assert.ok(rig.requests.some(r => r.url.endsWith("/api/tts")));
  assert.ok(!rig.requests.some(r => r.url.endsWith("/api/command")));
  assert.match(rig.element("motion-status").textContent, /AUDIO/);
  assert.notEqual(rig.element("voice-level").style.transform, "scaleX(0.000)");
});

test("motion preference persists and is restored on the next launch", () => {
  const rig = appRig({ reducedMotion: true });
  rig.element("motion-toggle").click();
  assert.equal(rig.storage.get("kira.motion"), "on");
  const reopened = appRig({ reducedMotion: true, motionPreference: rig.storage.get("kira.motion") });
  assert.equal(reopened.element("motion-toggle").textContent, "MOTION: ON");
  assert.equal(reopened.element("motion-status").textContent, "VOICE IDLE");
});

test("diagnostic controls remain interactive and CSS obeys reduced motion", () => {
  const css = readFileSync(new URL("../ui/style.css", import.meta.url), "utf8");
  assert.match(css, /\.speech-diagnostics\s*\{[^}]*pointer-events:\s*auto/);
  assert.match(css, /html\[data-motion='off'\]/);
  assert.match(css, /prefers-reduced-motion:reduce/);
});

test("API calls use relative URLs, including commands and speech", async () => {
  const rig = appRig();
  await rig.probe.sendCommand("hello");
  await flush();
  assert.ok(rig.requests.length > 4);
  for (const request of rig.requests) assert.ok(request.url.startsWith("/api/"), request.url);
});

test("model responses and operator text are rendered as text, never HTML", async () => {
  const rig = appRig();
  const message = rig.probe.addMessage("KIRA", '<img src=x onerror="alert(1)">');
  const content = message.children[1].children[1];
  assert.equal(content.innerHTML, "");
  assert.equal(content.textContent, '<img src=x onerror="alert(1)">');
});

test("unavailable telemetry resets readings instead of leaving stale values", async () => {
  let offline = false;
  const rig = appRig({ response: async (url) => url === "/api/system"
    ? offline ? { error: "offline" } : { cpu_percent: 12, memory_percent: 33, disk_percent: 40 }
    : {} });
  await flush();
  assert.equal(rig.element("cpu").textContent, "12.0%");
  offline = true;
  await rig.probe.updateTelemetry();
  assert.equal(rig.element("cpu").textContent, "—");
  assert.equal(rig.element("cpu-bar").style.width, "0%");
  assert.equal(rig.element("telemetry-live").textContent, "OFFLINE");
});

test("command requests cannot overlap or duplicate desktop side effects", async () => {
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  const rig = appRig({ response: url => url === "/api/command" ? pending : {} });
  const first = rig.probe.sendCommand("open chrome");
  await rig.probe.sendCommand("open chrome");
  assert.equal(rig.requests.filter(r => r.url === "/api/command").length, 1);
  rig.probe.setActivity("READY");
  assert.equal(rig.element("activity").textContent, "THINKING");
  release({ response: "Done." });
  await first;
  assert.equal(rig.element("send").disabled, false);
});

test("failed actions are not reported or spoken as completed", async () => {
  const rig = appRig({ response: async url => url === "/api/command" ? { action: "open_app", success: false } : {} });
  await rig.probe.sendCommand("open unknown app");
  await flush();
  assert.match(rig.element("conversation").textContent, /could not complete/);
  assert.equal(rig.requests.filter(r => r.url === "/api/tts").length, 0);
});

test("the live conversation is bounded without touching persisted history", () => {
  const rig = appRig();
  for (let i = 0; i < 120; i++) rig.probe.addMessage("KIRA", `Reply ${i}`);
  assert.equal(rig.element("conversation").children.length, 100);
  assert.ok(!rig.requests.some(r => r.init.method === "POST"));
});
