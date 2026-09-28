import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";
import { SpeechPlayer } from "../ui/speech.mjs";
import { AVATAR_BRIGHTNESS_DEFAULT } from "../ui/avatar.mjs";
import { playerRig } from "./support/speech-fakes.mjs";

// Run the actual app code, with lightweight rendering/DOM doubles. These tests
// check the wiring as well as the standalone envelope (not visual fidelity).
function appRig(options = {}) {
  const rig = playerRig(options);
  const elements = new Map(), listeners = new Map(), requests = [];
  const storage = new Map(options.motionPreference ? [["kira.motion", options.motionPreference]] : []);
  class Vector {
    constructor(x = 0, y = 0, z = 0) { this.set(x, y, z); }
    set(x, y, z) { this.x = x; this.y = y; this.z = z; }
    setScalar(n) { this.set(n, n, n); }
  }
  class Node {
    constructor(geometry, material) {
      this.geometry = geometry;
      this.material = material;
      this.position = new Vector(); this.rotation = new Vector(); this.scale = new Vector(1, 1, 1);
      this.children = [];
    }
    add(child) { this.children.push(child); }
    updateProjectionMatrix() {}
  }
  class Material {
    constructor(props) { Object.assign(this, props); }
    clone() { return new Material(this); }
  }
  class Geometry { setAttribute() {} }
  class Renderer {
    constructor() { this.domElement = {}; }
    setPixelRatio() {} setSize() {} render() {} addPass() {} clearDepth() {}
  }
  const drawing = { fillRect() {}, fillText() {} };
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      textContent: "", innerHTML: "", style: {}, value: "", children: [],
      classList: { add() {}, remove() {} },
      appendChild(child) { this.children.push(child); },
      addEventListener(name, fn) { this[name] = fn; },
      getContext: () => drawing,
    });
    return elements.get(id);
  }
  const mediaQuery = { matches: Boolean(options.reducedMotion) };
  const three = {
    Scene: Node, Group: Node, Mesh: Node, Points: Node, PerspectiveCamera: Node,
    SphereGeometry: Geometry, TorusGeometry: Geometry, BoxGeometry: Geometry,
    CylinderGeometry: Geometry, RingGeometry: Geometry, BufferGeometry: Geometry,
    BufferAttribute: Geometry, MeshBasicMaterial: Material, MeshStandardMaterial: Material,
    PointsMaterial: Material, PointLight: Node, AmbientLight: Node,
    WebGLRenderer: Renderer, Color: Vector, Vector2: Vector, Euler: Vector,
  };
  const context = vm.createContext({
    ...rig.env, THREE: three, AVATAR_BRIGHTNESS_DEFAULT,
    SpeechPlayer: class extends SpeechPlayer {
      constructor(options) { super({ ...options, env: rig.env }); }
    },
    EffectComposer: Renderer, RenderPass: Node, UnrealBloomPass: Node,
    console: { log() {}, error() {} },
    document: { getElementById: element, createElement: () => element(`new-${elements.size}`) },
    location: { protocol: "http:", hostname: "127.0.0.1" },
    innerWidth: 1280, innerHeight: 800, devicePixelRatio: 1,
    matchMedia: () => mediaQuery,
    localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    requestAnimationFrame() {}, setInterval() {},
    addEventListener(name, fn) { listeners.set(name, fn); },
    fetch: async (url, init) => {
      requests.push({ url, init });
      const data = url.endsWith("/api/tts") ? { audio: "YWJj" }
        : url.endsWith("/api/command") ? { response: "Hello there, sir." } : {};
      return { ok: true, json: async () => data };
    },
  });
  context.window = context;
  const source = readFileSync(new URL("../ui/app.js", import.meta.url), "utf8").replace(/^import .*;\n/gm, "");
  vm.runInContext(source + `\nglobalThis.probe = {
    speech, speak, stopSpeaking, sendCommand, setActivity, animate,
    core, neuralCore, coreGlow, reactor, voiceUniforms, energyMaterial,
  };`, context);
  return {
    ...rig, probe: context.probe, element, listeners, requests, storage,
    step(ms = 100) { rig.advance(ms); context.probe.animate(); },
  };
}

test("the actual reactor expands with speech and returns to its idle size", async () => {
  const rig = appRig();
  const before = rig.probe.core.scale.y;
  await rig.probe.speak("Hello there, sir.");
  rig.step();
  assert.ok(rig.probe.core.scale.y > before + 0.1, "speech never reached the rendered core");
  assert.ok(rig.probe.voiceUniforms.voiceEnergy.value > 0);
  assert.ok(rig.probe.neuralCore.scale.x > 1);
  rig.audios[0].onended();
  for (let i = 0; i < 25; i++) rig.step();
  assert.equal(rig.probe.voiceUniforms.voiceEnergy.value, 0);
  assert.ok(rig.probe.core.scale.y < 1.05);
  assert.equal(rig.element("activity").textContent, "READY");
});

test("the command handler's READY cannot overwrite active speech", async () => {
  const rig = appRig();
  await rig.probe.sendCommand("hello");
  // Flush the asynchronous /tts fetch, decoding and play promise.
  await new Promise(setImmediate);
  assert.equal(rig.audios.length, 1);
  assert.equal(rig.element("activity").textContent, "SPEAKING");
  rig.probe.setActivity("READY");
  assert.equal(rig.element("activity").textContent, "SPEAKING");
});

test("the mute button stops speech-driven motion and releases the audio", async () => {
  const rig = appRig();
  await rig.probe.speak("hello");
  rig.step();
  rig.element("mute").click();
  assert.equal(rig.probe.speech.enabled, false);
  assert.ok(rig.audios[0].paused);
  assert.equal(rig.revoked.length, 1);
  for (let i = 0; i < 25; i++) rig.step();
  assert.equal(rig.probe.voiceUniforms.voiceEnergy.value, 0);
});

test("reduced motion removes speech deformation and displacement", async () => {
  const rig = appRig({ reducedMotion: true });
  await rig.probe.speak("hello");
  rig.step();
  assert.equal(rig.probe.core.scale.y, 1);
  assert.equal(rig.probe.reactor.position.y, 0);
  assert.equal(rig.probe.voiceUniforms.voiceEnergy.value, 0);
  assert.equal(rig.probe.voiceUniforms.voiceTime.value, 0);
});

test("the energy-shell shader uses the same live audio uniforms", () => {
  const rig = appRig();
  const shader = { uniforms: {}, vertexShader: "#include <begin_vertex>" };
  rig.probe.energyMaterial.onBeforeCompile(shader);
  assert.equal(shader.uniforms.voiceEnergy, rig.probe.voiceUniforms.voiceEnergy);
  assert.match(shader.vertexShader, /transformed \+= normal/);
  assert.match(shader.vertexShader, /voiceLow \* 0\.16/);
});

test("page exit cleans up the real app's audio session", async () => {
  const rig = appRig();
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
  assert.ok(rig.probe.reactor.scale.y > 1.1, "the whole neuron should visibly breathe");
  assert.match(rig.element("motion-status").textContent, /AUDIO/);
});

test("Test Motion checks the renderer without audio, network or Ollama", () => {
  const rig = appRig();
  const beforeRequests = rig.requests.length;
  rig.element("motion-test").click();
  rig.step(500);
  assert.ok(rig.probe.reactor.scale.y > 1.08);
  assert.equal(rig.audios.length, 0);
  assert.equal(rig.requests.length, beforeRequests);
  assert.match(rig.element("motion-status").textContent, /TEST MOTION/);
  rig.step(4000);
  assert.equal(rig.probe.reactor.scale.y, 1.05);
});

test("Motion Off is respected during the visual test", () => {
  const rig = appRig();
  rig.element("motion-toggle").click(); // on
  rig.element("motion-toggle").click(); // off
  rig.element("motion-test").click();
  rig.step(500);
  assert.equal(rig.probe.reactor.scale.y, 1.05);
  assert.match(rig.element("motion-status").textContent, /MOTION OFF/);
});

test("Test Voice exercises speech without sending a desktop command", async () => {
  const rig = appRig();
  rig.element("voice-test").click();
  await new Promise(setImmediate);
  rig.step();
  assert.equal(rig.audios.length, 1);
  assert.ok(rig.requests.some(r => r.url.endsWith("/api/tts")));
  assert.ok(!rig.requests.some(r => r.url.endsWith("/api/command")));
  assert.match(rig.element("motion-status").textContent, /AUDIO/);
  assert.notEqual(rig.element("voice-level").style.transform, "scaleX(0.000)");
});


test("explicit motion preference persists and is restored on the next launch", () => {
  const rig = appRig({ reducedMotion: true });
  rig.element("motion-toggle").click();
  assert.equal(rig.storage.get("kira.motion"), "on");
  const reopened = appRig({ reducedMotion: true, motionPreference: rig.storage.get("kira.motion") });
  assert.equal(reopened.element("motion-toggle").textContent, "MOTION: ON");
  assert.equal(reopened.element("motion-status").textContent, "VOICE IDLE");
});

test("diagnostic controls opt back into pointer events inside the HUD", () => {
  const css = readFileSync(new URL("../ui/style.css", import.meta.url), "utf8");
  assert.match(css, /\.speech-diagnostics\s*\{[^}]*pointer-events:\s*auto/);
});

test("MED French voice preference reaches the neural speech request", async () => {
  const rig = appRig();
  rig.storage.set("kira.voice", "denise");
  await rig.probe.speak("Bonjour !");
  const request = rig.requests.find(item => item.url.endsWith("/api/tts"));
  const body = JSON.parse(request.init.body);
  assert.equal(body.voice, "denise");
  assert.equal(body.language, "fr-FR");
  assert.equal(rig.probe.speech.session.language, "fr-FR");
});
