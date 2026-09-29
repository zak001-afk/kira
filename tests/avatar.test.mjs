import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";
import { SpeechPlayer } from "../ui/speech.mjs";
import { LipMotion, REST_MOUTH, lipDemoPose } from "../ui/lips.mjs";
import { AVATAR_PORTRAIT, AVATAR_BRIGHTNESS_DEFAULT, createPortraitMaterial } from "../ui/avatar.mjs";
import { MOUTH_REGION } from "../ui/holo-mouth.mjs";
import { playerRig } from "./support/speech-fakes.mjs";

// Run the actual app AND mouth renderer with small Three.js/DOM doubles.
// Pixel/colour checks in a real WebGL browser live in cockpit_browser.py.
function avatarRig(options = {}) {
  const rig = playerRig(options);
  const elements = new Map(), materials = [], loads = [], renders = [], errors = [];
  const storage = new Map(Object.entries(options.stored || {}));
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
    add(child) { this.children.push(child); child.parent = this; }
    remove(child) { this.children = this.children.filter(item => item !== child); child.parent = null; }
    updateProjectionMatrix() {}
  }
  class Material {
    constructor(props) { Object.assign(this, props); materials.push(this); }
    clone() { return new Material(this); }
    dispose() { this.disposed = true; }
  }
  class Geometry {
    constructor(width, height) { this.parameters = { width, height }; }
    setAttribute() {}
    dispose() { this.disposed = true; }
  }
  class Texture {
    constructor(image) { this.image = image; this.needsUpdate = false; }
    dispose() { this.disposed = true; }
  }
  class TextureLoader {
    load(url, onLoad) {
      const image = { naturalWidth: 1024, naturalHeight: 1024, src: url };
      const texture = new Texture(image);
      // Like the real TextureLoader, deliver after the plane has been created.
      loads.push(() => onLoad?.(texture));
      return texture;
    }
  }
  class Renderer {
    constructor() { this.domElement = {}; this.autoClear = true; }
    setPixelRatio() {} setSize() {} addPass() {}
    render(scene) { renders.push({ type: "portrait", scene, autoClear: this.autoClear }); }
    clearDepth() { renders.push({ type: "clearDepth" }); }
  }
  class Composer extends Renderer {
    render() { renders.push({ type: "bloom" }); }
  }
  function drawing() {
    const gradient = () => ({ addColorStop() {} });
    return {
      fillRect() {}, fillText() {}, clearRect() {}, drawImage() {},
      save() {}, restore() {}, beginPath() {}, closePath() {},
      moveTo() {}, lineTo() {}, clip() {}, fill() {}, ellipse() {}, roundRect() {},
      setTransform() {}, createRadialGradient: gradient, createLinearGradient: gradient,
    };
  }
  function element(id) {
    if (!elements.has(id)) {
      const context = drawing();
      elements.set(id, {
        textContent: "", innerHTML: "", style: {}, value: "", children: [],
        classList: { add() {}, remove() {} },
        appendChild(child) { this.children.push(child); },
        addEventListener(name, fn) { this[name] = fn; },
        getContext: () => context,
      });
    }
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
    NoColorSpace: "", NormalBlending: "normal", LinearFilter: "linear",
  };
  const context = vm.createContext({
    ...rig.env, THREE: three, AVATAR_PORTRAIT, AVATAR_BRIGHTNESS_DEFAULT, createPortraitMaterial,
    LipMotion, REST_MOUTH, lipDemoPose,
    SpeechPlayer: class extends SpeechPlayer {
      constructor(options) { super({ ...options, env: rig.env }); }
    },
    EffectComposer: Composer, RenderPass: Node, UnrealBloomPass: Node,
    console: { log() {}, error: (...args) => errors.push(args) },
    document: { getElementById: element, createElement: () => element(`new-${elements.size}`) },
    location: { protocol: "http:", hostname: "127.0.0.1" },
    innerWidth: 1280, innerHeight: 800, devicePixelRatio: 1,
    matchMedia: () => ({ matches: false }),
    localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    requestAnimationFrame() {}, setInterval() {}, addEventListener() {},
    fetch: async () => ({ ok: true, json: async () => ({}) }),
  });
  context.window = context;
  const stripImports = source => source.replace(/^import .*;\n/gm, "");
  const mouthSource = stripImports(readFileSync(new URL("../ui/holo-mouth.mjs", import.meta.url), "utf8"))
    .replace(/^export /gm, "");
  vm.runInContext(`globalThis.HoloMouth = (() => { ${mouthSource}\nreturn HoloMouth; })();`, context);
  const source = stripImports(readFileSync(new URL("../ui/app.js", import.meta.url), "utf8"));
  vm.runInContext(source + `\nglobalThis.probe = {
    animate, renderer, scene, avatarScene, avatarGroup, bloomPass,
    get mouth() { return holoMouth; }, avatarBrightness: () => avatarBrightness,
  };`, context);
  loads.forEach(load => load());
  assert.deepEqual(errors, [], "the real mouth renderer failed to load");
  const material = materials.find(item => item.uniforms?.brightness);
  assert.ok(material, "the portrait material was never built");
  assert.ok(context.probe.mouth?.ready, "the lip mesh was not built for the new portrait");
  return { ...rig, probe: context.probe, material, element, storage, renders };
}

test("the active portrait is a bundled, compact WebP, not the metallic avatar", () => {
  const rig = avatarRig();
  assert.equal(rig.material.uniforms.map.value.image.src, AVATAR_PORTRAIT.url);
  assert.match(AVATAR_PORTRAIT.url, /^assets\/avatar-natural\.webp\?/);
  const bytes = readFileSync(new URL(`../ui/${AVATAR_PORTRAIT.url.split("?")[0]}`, import.meta.url));
  assert.equal(bytes.toString("ascii", 0, 4), "RIFF");
  assert.equal(bytes.toString("ascii", 8, 12), "WEBP");
  assert.ok(bytes.length < 500_000);
});

test("the natural portrait starts at 90 % in both materials and the settings", () => {
  const rig = avatarRig();
  assert.equal(rig.probe.avatarBrightness(), 0.9);
  assert.equal(rig.material.uniforms.brightness.value, 0.9);
  assert.equal(rig.probe.mouth.overlay.material.uniforms.brightness.value, 0.9);
  assert.equal(rig.element("avatar-brightness").value, "90");
  assert.equal(rig.element("avatar-brightness-value").textContent, "90 %");
  const html = readFileSync(new URL("../ui/index.html", import.meta.url), "utf8");
  assert.match(html, /id="avatar-brightness"[^>]*value="90"/);
  assert.match(html, /id="avatar-brightness-value">90 %/);
});

test("saved brightness, including the previous 45 %, still wins over the default", () => {
  for (const value of [0.1, 0.45, 0.8, 1]) {
    const rig = avatarRig({ stored: { "kira.avatarBrightness": String(value) } });
    assert.equal(rig.probe.avatarBrightness(), value);
    assert.equal(rig.material.uniforms.brightness.value, value);
    assert.equal(rig.element("avatar-brightness").value, String(value * 100));
  }
});

test("out-of-range brightness preferences cannot black out or overexpose the face", () => {
  for (const value of ["NaN", "Infinity", "0", "-1", "0.09", "1.1", "invalid"]) {
    const rig = avatarRig({ stored: { "kira.avatarBrightness": value } });
    assert.equal(rig.probe.avatarBrightness(), AVATAR_BRIGHTNESS_DEFAULT);
  }
});

test("the brightness slider updates the face and speaking lips together and persists", () => {
  const rig = avatarRig();
  const face = rig.material.uniforms.brightness;
  const lips = rig.probe.mouth.overlay.material.uniforms.brightness;
  assert.equal(face, lips, "brightness must be a shared uniform, not copied on one frame");
  for (const value of [10, 45, 80, 100]) {
    rig.element("avatar-brightness").value = String(value);
    rig.element("avatar-brightness").input();
    assert.equal(face.value, value / 100);
    assert.equal(lips.value, value / 100);
    assert.equal(rig.element("avatar-brightness-value").textContent, `${value} %`);
    assert.equal(rig.storage.get("kira.avatarBrightness"), String(value / 100));
  }
});

test("face and lips preserve photograph RGB and alpha with no green tint or distortion", () => {
  const rig = avatarRig();
  const mouthMaterial = rig.probe.mouth.overlay.material;
  assert.equal(rig.material.fragmentShader, mouthMaterial.fragmentShader);
  assert.equal(rig.material.vertexShader, mouthMaterial.vertexShader);
  for (const material of [rig.material, mouthMaterial]) {
    assert.match(material.fragmentShader, /vec4\(portrait\.rgb \* brightness, portrait\.a\)/);
    assert.doesNotMatch(material.fragmentShader, /luma|green|sin\(|smoothstep|glitch|scanline|dot\(/i);
    assert.doesNotMatch(material.vertexShader, /time|sin\(|step\(/);
    assert.deepEqual(Object.keys(material.uniforms), ["map", "brightness"]);
    assert.equal(material.toneMapped, false);
    assert.equal(material.blending, "normal");
    assert.equal(material.uniforms.map.value.colorSpace, "");
  }
});

test("the photographic face is composed after bloom, without clearing the green decor", () => {
  const rig = avatarRig();
  assert.ok(!rig.probe.scene.children.includes(rig.probe.avatarGroup));
  assert.ok(rig.probe.avatarScene.children.includes(rig.probe.avatarGroup));
  rig.renders.length = 0;
  rig.probe.animate();
  assert.deepEqual(rig.renders.map(render => render.type), ["bloom", "clearDepth", "portrait"]);
  assert.equal(rig.renders[2].scene, rig.probe.avatarScene);
  assert.equal(rig.renders[2].autoClear, false);
  assert.equal(rig.probe.renderer.autoClear, true, "the next background frame must still clear");
  const before = rig.probe.bloomPass.strength;
  rig.element("avatar-brightness").value = "10";
  rig.element("avatar-brightness").input();
  rig.probe.animate();
  assert.equal(rig.probe.bloomPass.strength, before, "skin brightness must not recolour/dim the HUD");
});

test("the animated mouth aligns with the patch rectangle, not the mouth's off-centre slit", () => {
  const rig = avatarRig();
  const plane = rig.probe.avatarGroup.children[0];
  const overlay = rig.probe.mouth.overlay;
  assert.equal(overlay.parent, plane);
  assert.equal(overlay.position.z, 0, "coplanar geometry avoids perspective drift");
  assert.equal(overlay.position.x, ((MOUTH_REGION.x + MOUTH_REGION.width / 2) / 1024 - 0.5) * 6.4);
  assert.equal(overlay.position.y, (0.5 - (MOUTH_REGION.y + MOUTH_REGION.height / 2) / 1024) * 6.4);
  assert.equal(overlay.geometry.parameters.width, MOUTH_REGION.width / 1024 * 6.4);
  assert.equal(overlay.geometry.parameters.height, MOUTH_REGION.height / 1024 * 6.4);
  assert.equal(overlay.renderOrder, plane.renderOrder + 1);
  assert.equal(overlay.material.depthTest, false);
  assert.equal(overlay.material.depthWrite, false);
});

test("the new mouth follows the visual demo, resets and releases its render resources", () => {
  const rig = avatarRig();
  const mouth = rig.probe.mouth;
  rig.element("motion-test").click();
  rig.advance(1000);
  rig.probe.animate();
  assert.ok(mouth.pose.open > 0);
  assert.equal(mouth.texture.needsUpdate, true);
  rig.element("motion-toggle").click(); // on
  rig.element("motion-toggle").click(); // off
  rig.probe.animate();
  assert.equal(mouth.pose.open, 0);
  mouth.destroy();
  assert.equal(mouth.overlay.parent, null);
  assert.equal(mouth.overlay.material.disposed, true);
  assert.equal(mouth.overlay.geometry.disposed, true);
  assert.equal(mouth.texture.disposed, true);
});
