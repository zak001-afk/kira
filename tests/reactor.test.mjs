import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";
import { SpeechPlayer } from "../ui/speech.mjs";
import { playerRig } from "./support/speech-fakes.mjs";

// Run the actual app code, with lightweight rendering/DOM doubles. These tests
// check the wiring as well as the standalone envelope (not visual fidelity).
function appRig(options = {}) {
  const rig = playerRig(options);
  const elements = new Map(), listeners = new Map(), requests = [];
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
    setPixelRatio() {} setSize() {} render() {} addPass() {}
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
    ...rig.env, THREE: three,
    SpeechPlayer: class extends SpeechPlayer {
      constructor(options) { super({ ...options, env: rig.env }); }
    },
    EffectComposer: Renderer, RenderPass: Node, UnrealBloomPass: Node,
    console: { log() {}, error() {} },
    document: { getElementById: element, createElement: () => element(`new-${elements.size}`) },
    location: { protocol: "http:", hostname: "127.0.0.1" },
    innerWidth: 1280, innerHeight: 800, devicePixelRatio: 1,
    matchMedia: () => mediaQuery,
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
    ...rig, probe: context.probe, element, listeners, requests,
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
