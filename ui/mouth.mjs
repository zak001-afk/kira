import { LipMotion, REST_MOUTH } from "./lips.mjs";

// These landmarks belong to the bundled 896 × 1200 portrait, not an arbitrary
// uploaded face. Only a small lower-face patch is composited, and only while
// speaking. Original lip/skin pixels move on a mesh; the teeth are photographic.
export const PORTRAIT_SIZE = Object.freeze({ width: 896, height: 1200 });
export const MOUTH_REGION = Object.freeze({ x: 296, y: 688, width: 304, height: 224 });
const COUNT = 32;
const CX = 447 - MOUTH_REGION.x;
const CY = 761.8 - MOUTH_REGION.y;
const bounded = n => Math.min(1, Math.max(0, Number.isFinite(n) ? n : 0));

export function createMouthMesh() {
  const vertices = new Float32Array(COUNT * 4 * 2);
  const triangles = [];
  for (let ring = 0; ring < 4; ring++) {
    for (let i = 0; i < COUNT; i++) {
      const angle = i / COUNT * Math.PI * 2;
      const c = Math.cos(angle), s = Math.sin(angle);
      let x, y;
      if (ring === 0) {
        x = CX + 89 * c;
        y = CY - Math.cos(2 * angle) + (s < 0 ? 1.8 : 2.1) * s;
      } else if (ring === 1) {
        x = CX + 98 * c;
        y = CY + (s < 0 ? 35 : 39) * s + (s < 0 ? 9 * Math.exp(-((c / 0.2) ** 2)) : 0);
      } else if (ring === 2) {
        x = CX + 136 * c;
        y = CY + (s < 0 ? 62 : 99) * s;
      } else {
        const dx = Math.abs(c) < 1e-6 ? Infinity : (c > 0 ? MOUTH_REGION.width - CX : -CX) / c;
        const dy = Math.abs(s) < 1e-6 ? Infinity : (s > 0 ? MOUTH_REGION.height - CY : -CY) / s;
        const distance = Math.min(dx, dy);
        x = CX + distance * c;
        y = CY + distance * s;
      }
      const index = (ring * COUNT + i) * 2;
      vertices[index] = x; vertices[index + 1] = y;
      if (ring < 3) {
        const a = ring * COUNT + i, b = ring * COUNT + (i + 1) % COUNT;
        const d = a + COUNT, e = b + COUNT;
        triangles.push([a, b, d], [b, e, d]);
      }
    }
  }
  return { vertices, triangles };
}
const MESH = createMouthMesh();

export function deformMouth(pose, output = new Float32Array(MESH.vertices.length)) {
  const open = bounded(pose.open), round = bounded(pose.round), wide = bounded(pose.wide);
  const press = bounded(pose.press), bite = bounded(pose.bite);
  for (let ring = 0; ring < 4; ring++) {
    for (let i = 0; i < COUNT; i++) {
      const index = (ring * COUNT + i) * 2;
      const x = MESH.vertices[index], y = MESH.vertices[index + 1];
      const angle = i / COUNT * Math.PI * 2;
      const s = Math.sin(angle), c = Math.cos(angle);
      const influence = [1, 0.96, 0.25, 0][ring];
      output[index] = CX + (x - CX) * (1 + (wide * 0.15 - round * 0.32 - press * 0.015) * influence);
      let dy = 0;
      if (ring <= 1) {
        dy = open * (s >= 0 ? 3 + 28 * s : (ring === 0 ? 10 : 6) * s + 3 * c * c);
        dy += round * s * 2;
        if (ring === 0) {
          const seam = CY - Math.cos(2 * angle);
          dy += press * (seam + s * 0.15 - y);
          if (s > 0) dy -= bite * Math.min(7, open * 18) * s;
        } else {
          dy -= press * s * 1.6;
          if (s > 0) dy -= bite * s * 2;
        }
      } else if (ring === 2) {
        dy = open * (s > 0 ? 9 : 1.5) * s;
      }
      output[index + 1] = y + dy;
    }
  }
  return output;
}

export function fitMouthRegion(width, height) {
  const scale = Math.min(width / PORTRAIT_SIZE.width, height / PORTRAIT_SIZE.height);
  return {
    left: (width - PORTRAIT_SIZE.width * scale) / 2 + MOUTH_REGION.x * scale,
    top: (height - PORTRAIT_SIZE.height * scale) / 2 + MOUTH_REGION.y * scale,
    width: MOUTH_REGION.width * scale,
    height: MOUTH_REGION.height * scale,
  };
}

function triangle(context, texture, source, destination, indices) {
  const [i, j, k] = indices.map(index => index * 2);
  const sx = source[i], sy = source[i + 1], dx = destination[i], dy = destination[i + 1];
  const ux = source[j] - sx, uy = source[j + 1] - sy, vx = source[k] - sx, vy = source[k + 1] - sy;
  const dux = destination[j] - dx, duy = destination[j + 1] - dy;
  const dvx = destination[k] - dx, dvy = destination[k + 1] - dy;
  const determinant = ux * vy - uy * vx;
  if (Math.abs(determinant) < 0.0001 || Math.abs(dux * dvy - duy * dvx) < 0.00001) return;
  const a = (dux * vy - dvx * uy) / determinant;
  const b = (duy * vy - dvy * uy) / determinant;
  const c = (dvx * ux - dux * vx) / determinant;
  const d = (dvy * ux - duy * vx) / determinant;
  // A subpixel overlap prevents antialias seams between adjacent textured facets.
  const mx = (destination[i] + destination[j] + destination[k]) / 3;
  const my = (destination[i + 1] + destination[j + 1] + destination[k + 1]) / 3;
  context.save();
  context.beginPath();
  [i, j, k].forEach((index, n) => {
    const x = destination[index], y = destination[index + 1];
    const length = Math.hypot(x - mx, y - my) || 1;
    const px = x + (x - mx) / length * 0.45, py = y + (y - my) / length * 0.45;
    if (n) context.lineTo(px, py); else context.moveTo(px, py);
  });
  context.closePath();
  context.clip();
  context.setTransform(a, b, c, d, dx - a * sx - c * sy, dy - b * sx - d * sy);
  context.drawImage(texture, 0, 0);
  context.restore();
}

export class MouthRenderer {
  constructor(document) {
    this.document = document;
    this.canvas = document.getElementById("mouth-canvas");
    this.image = document.getElementById("portrait-image");
    this.interior = document.getElementById("mouth-texture");
    this.state = "unsupported";
    this.lastKey = "";
    this.pose = { ...REST_MOUTH };
    this.destroyed = false;
    try { this.context = this.canvas?.getContext?.("2d"); } catch { /* Audio must still work. */ }
    if (!this.context || !this.image) return;
    this.state = "loading";
    this.canvas.width = MOUTH_REGION.width;
    this.canvas.height = MOUTH_REGION.height;
    this.base = document.createElement("canvas");
    this.base.width = this.canvas.width; this.base.height = this.canvas.height;
    this.mask = document.createElement("canvas");
    this.mask.width = this.canvas.width; this.mask.height = this.canvas.height;
    this.destination = new Float32Array(MESH.vertices.length);
    this.innerSource = new Float32Array((COUNT + 1) * 2);
    this.innerDestination = new Float32Array(this.innerSource.length);
    for (let i = 0; i < COUNT; i++) {
      const angle = i / COUNT * Math.PI * 2, s = Math.sin(angle);
      // Coordinates in the 180 × 62 oral photograph, not the full portrait.
      this.innerSource[i * 2] = 90 + 80 * Math.cos(angle);
      this.innerSource[i * 2 + 1] = 30 + (s < 0 ? 20 : 25) * s;
    }
    this.innerSource[COUNT * 2] = 90; this.innerSource[COUNT * 2 + 1] = 30;
    this.buildMask();
    this.onLoad = () => { if (!this.destroyed) { this.prepare(); this.lastKey = ""; this.render(this.pose); } };
    this.onError = () => { if (!this.destroyed) { this.state = this.ready ? "fallback" : "unavailable"; } };
    this.image.addEventListener("load", this.onLoad);
    this.image.addEventListener("error", this.onError);
    this.interior?.addEventListener("load", this.onLoad);
    this.interior?.addEventListener("error", this.onError);
    const Observer = document.defaultView?.ResizeObserver;
    if (Observer) { this.observer = new Observer(() => this.fit()); this.observer.observe(this.image); }
    this.prepare();
  }

  buildMask() {
    const context = this.mask.getContext("2d");
    const { width, height } = this.mask;
    const horizontal = context.createLinearGradient(0, 0, width, 0);
    horizontal.addColorStop(0, "transparent"); horizontal.addColorStop(0.055, "black");
    horizontal.addColorStop(0.945, "black"); horizontal.addColorStop(1, "transparent");
    context.fillStyle = horizontal; context.fillRect(0, 0, width, height);
    context.globalCompositeOperation = "destination-in";
    const vertical = context.createLinearGradient(0, 0, 0, height);
    vertical.addColorStop(0, "transparent"); vertical.addColorStop(0.07, "black");
    vertical.addColorStop(0.9, "black"); vertical.addColorStop(1, "transparent");
    context.fillStyle = vertical; context.fillRect(0, 0, width, height);
  }

  prepare() {
    if (!this.context || this.destroyed || !this.image.complete || !this.image.naturalWidth) return;
    if (this.image.naturalWidth !== PORTRAIT_SIZE.width || this.image.naturalHeight !== PORTRAIT_SIZE.height) {
      this.state = "unavailable"; return; // Don't place a mouth on an unrelated image.
    }
    const r = MOUTH_REGION;
    this.base.getContext("2d").drawImage(this.image, r.x, r.y, r.width, r.height, 0, 0, r.width, r.height);
    this.ready = true;
    this.state = this.interior?.complete && this.interior.naturalWidth ? "ready" : "fallback";
    this.fit();
  }

  fit() {
    if (!this.image || !this.canvas) return;
    const box = fitMouthRegion(this.image.clientWidth, this.image.clientHeight);
    for (const key of ["left", "top", "width", "height"]) this.canvas.style[key] = `${box[key]}px`;
  }

  render(pose) {
    this.pose = { ...pose };
    if (this.destroyed || !this.canvas) return;
    const keys = ["open", "round", "wide", "bite", "press"];
    for (const key of keys) this.pose[key] = bounded(this.pose[key]);
    this.canvas.dataset.viseme = pose.viseme || "REST";
    this.canvas.dataset.open = this.pose.open.toFixed(3);
    this.canvas.dataset.renderer = this.state;
    const key = keys.map(name => this.pose[name].toFixed(3)).join("/");
    if (key === this.lastKey) return;
    this.lastKey = key;
    const idle = keys.every(name => this.pose[name] < 0.001);
    this.canvas.hidden = !this.ready || idle;
    if (!this.ready || !this.context || idle) return;
    const context = this.context;
    context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    deformMouth(this.pose, this.destination);
    this.innerDestination.set(this.destination.subarray(0, COUNT * 2));
    let x = 0, y = 0;
    for (let i = 0; i < COUNT; i++) { x += this.destination[i * 2]; y += this.destination[i * 2 + 1]; }
    this.innerDestination[COUNT * 2] = x / COUNT;
    this.innerDestination[COUNT * 2 + 1] = y / COUNT;
    if (this.interior?.complete && this.interior.naturalWidth) {
      for (let i = 0; i < COUNT; i++) triangle(context, this.interior, this.innerSource, this.innerDestination, [COUNT, i, (i + 1) % COUNT]);
    } else {
      context.fillStyle = "#04070a"; context.beginPath();
      for (let i = 0; i < COUNT; i++) context.lineTo(this.destination[i * 2], this.destination[i * 2 + 1]);
      context.closePath(); context.fill();
    }
    for (const indices of MESH.triangles) triangle(context, this.base, MESH.vertices, this.destination, indices);
    context.globalCompositeOperation = "destination-in";
    context.drawImage(this.mask, 0, 0);
    context.globalCompositeOperation = "source-over";
  }

  reset() { this.lastKey = ""; this.render(REST_MOUTH); }
  destroy() {
    this.reset();
    this.destroyed = true;
    this.observer?.disconnect();
    this.image?.removeEventListener?.("load", this.onLoad);
    this.image?.removeEventListener?.("error", this.onError);
    this.interior?.removeEventListener?.("load", this.onLoad);
    this.interior?.removeEventListener?.("error", this.onError);
  }
}

export class MouthAnimator {
  constructor(document) { this.motion = new LipMotion(); this.renderer = new MouthRenderer(document); }
  update(voice, options) { const pose = this.motion.sample(voice, options); this.renderer.render(pose); return pose; }
  reset() { this.motion.reset(); this.renderer.reset(); }
  destroy() { this.motion.reset(); this.renderer.destroy(); }
}
