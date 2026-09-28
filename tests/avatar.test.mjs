import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";
import { SpeechPlayer } from "../ui/speech.mjs";
import { playerRig } from "./support/speech-fakes.mjs";

// Runs the real ui/app.js with lightweight Three.js/DOM doubles and inspects the
// hologram the avatar is built from. The avatar itself is a source image, so these
// checks pin the render budget of its shader (default lightness, sharpening and
// relief on the face, how discreet the scanlines and glitch stay) instead of pixels.
function avatarRig(options = {}) {
  const rig = playerRig(options);
  const elements = new Map();
  const materials = [];
  const textures = [];
  const storage = new Map(Object.entries(options.stored || {}));
  const geometries = [];
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
    constructor(props) { Object.assign(this, props); this.isShaderMaterial = Boolean(this.fragmentShader); materials.push(this); }
    clone() { return new Material(this); }
  }
  class Geometry {
    constructor(width, height) { this.parameters = { width, height }; geometries.push(this); }
    setAttribute() {}
  }
  class Texture {
    constructor(image) { this.image = image; this.needsUpdate = false; textures.push(this); }
  }
  class TextureLoader {
    load(url, onLoad) {
      const image = { naturalWidth: 1024, naturalHeight: 1024, src: url };
      const texture = new Texture(image);
      onLoad?.(texture);
      return texture;
    }
  }
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
  const three = {
    Scene: Node, Group: Node, Mesh: Node, Points: Node, PerspectiveCamera: Node,
    SphereGeometry: Geometry, TorusGeometry: Geometry, BoxGeometry: Geometry,
    CylinderGeometry: Geometry, RingGeometry: Geometry, BufferGeometry: Geometry,
    PlaneGeometry: Geometry, BufferAttribute: Geometry,
    MeshBasicMaterial: Material, MeshStandardMaterial: Material, PointsMaterial: Material,
    ShaderMaterial: Material, CanvasTexture: Texture, TextureLoader,
    PointLight: Node, AmbientLight: Node,
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
    matchMedia: () => ({ matches: false }),
    localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    requestAnimationFrame() {}, setInterval() {},
    addEventListener() {},
    fetch: async () => ({ ok: true, json: async () => ({}) }),
  });
  context.window = context;
  const source = readFileSync(new URL("../ui/app.js", import.meta.url), "utf8").replace(/^import .*;\n/gm, "");
  vm.runInContext(source + "\nglobalThis.probe = { applyAvatarBrightness, avatarBrightness: () => avatarBrightness };\n", context);
  const material = materials.find(item => item.uniforms && item.uniforms.brightness);
  assert.ok(material, "the avatar hologram material was never built");
  return { ...rig, probe: context.probe, material, element, storage };
}

const glsl = rig => rig.material.fragmentShader;
const constant = (shader, name) => {
  const found = shader.match(new RegExp(`${name}\\s*=\\s*([-0-9.]+)`));
  assert.ok(found, `${name} is missing from the avatar shader`);
  return Number(found[1]);
};

test("the avatar starts at 45 % lightness, in the shader and in the settings", () => {
  const rig = avatarRig();
  assert.equal(rig.probe.avatarBrightness(), 0.45);
  assert.equal(rig.material.uniforms.brightness.value, 0.45);
  assert.equal(rig.element("avatar-brightness").value, "45");
  assert.equal(rig.element("avatar-brightness-value").textContent, "45 %");
});

test("a saved lightness preference still wins over the default", () => {
  const rig = avatarRig({ stored: { "kira.avatarBrightness": "0.8" } });
  assert.equal(rig.probe.avatarBrightness(), 0.8);
  assert.equal(rig.material.uniforms.brightness.value, 0.8);
  assert.equal(rig.element("avatar-brightness").value, "80");
});

test("the face keeps its sharpening, modelling, relief and lively skin", () => {
  const shader = glsl(avatarRig());
  assert.ok(constant(shader, "DETAIL_GAIN") >= 0.15, "fine detail must be sharpened");
  assert.ok(constant(shader, "MODEL_GAIN") >= 0.25, "the modelling of the face is lost");
  assert.ok(constant(shader, "RELIEF_GAIN") > 0, "the face lost its relief");
  assert.ok(constant(shader, "VIVID_GAIN") > 0, "the skin tint is not vivified");
  // Soft/hard bands come from the mipmaps of the same texture: no extra blur, and
  // the sharpening stays on the face instead of re-graining the whole background.
  assert.match(shader, /texture2D\(map, uv, SOFT_LOD\)/);
  assert.match(shader, /texture2D\(map, uv, MODEL_LOD\)/);
  assert.match(shader, /\* weight/);
});

test("scanlines and glitch stay discreet on the hologram", () => {
  const rig = avatarRig();
  const shader = glsl(rig);
  assert.ok(constant(shader, "SCANLINE_AMP") <= 0.04, "the scanlines are too deep to read as a face");
  assert.ok(constant(shader, "GLITCH_UV") <= 0.008, "the glitch shifts the face too far");
  assert.ok(constant(shader, "SCANLINE_AMP") >= 0.02, "the hologram should keep its projection texture");
  assert.doesNotMatch(shader, /0\.93 \+ 0\.07/, "the old 7 % scanline modulation is back");
  // The vertex-stage band displacement is part of the same glitch budget: rarely
  // triggered (0.985) and tiny (0.004) so the projection never tears apart.
  assert.match(rig.material.vertexShader, /0\.004 \* step\(0\.985/);
});
