import { LipMotion, REST_MOUTH } from "./lips.mjs";

// Portrait 896x1200 - bouche naturelle humaine améliorée
// Landmarks originaux conservés pour compatibilité tests, mais déformation naturelle
export const PORTRAIT_SIZE = Object.freeze({ width: 896, height: 1200 });
export const MOUTH_REGION = Object.freeze({ x: 296, y: 554, width: 304, height: 224 });
const COUNT = 32;
const CX = 447 - MOUTH_REGION.x;
const CY = 649 - MOUTH_REGION.y;
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
        // Bord interne - fente avec léger arc de Cupidon
        const cupid = Math.cos(2 * angle) * 0.8;
        x = CX + 52 * c;
        y = CY + cupid * 0.5 + (s < 0 ? 1.6 : 2.2) * s;
      } else if (ring === 1) {
        const upperThick = 8 + 3 * Math.exp(-(c*c)/0.18);
        const lowerThick = 14;
        x = CX + 62 * c;
        y = CY + (s < 0 ? upperThick * s + 5 * Math.exp(-((c/0.22)**2)) : lowerThick * s);
      } else if (ring === 2) {
        x = CX + 90 * c;
        y = CY + (s < 0 ? 34 * s : 58 * s);
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

// Déformation anatomique naturelle: lèvre sup stable, inf suit mâchoire, coins étirent
export function deformMouth(pose, output = new Float32Array(MESH.vertices.length)) {
  const open = bounded(pose.open), round = bounded(pose.round), wide = bounded(pose.wide);
  const press = bounded(pose.press), bite = bounded(pose.bite);
  const jawDrop = open * (0.88 + 0.12 * Math.sin(open * Math.PI * 0.5));
  const lipStretch = wide * 0.85 - round * 0.55;

  for (let ring = 0; ring < 4; ring++) {
    for (let i = 0; i < COUNT; i++) {
      const index = (ring * COUNT + i) * 2;
      const x = MESH.vertices[index], y = MESH.vertices[index + 1];
      const angle = i / COUNT * Math.PI * 2;
      const s = Math.sin(angle), c = Math.cos(angle);
      const isUpper = s < 0;
      const cornerFactor = Math.abs(c);
      const influence = [1, 0.92, 0.32, 0][ring];

      // Horizontal: coins bougent plus - effet renforcé pour test + naturel
      let xDeform = 0;
      if (ring <= 1) {
        const wideEffect = lipStretch * (0.3 + 0.7 * cornerFactor) * 26 * influence;
        const roundEffect = -round * cornerFactor * 28 * influence;
        xDeform = wideEffect + roundEffect - press * cornerFactor * 4 * influence;
      }
      output[index] = CX + (x - CX) * (1 + xDeform * 0.012) + xDeform * 0.22;

      // Vertical: anatomique
      let dy = 0;
      if (ring === 0) {
        if (isUpper) {
          dy = -jawDrop * (2.2 + 3.2 * (1 - cornerFactor)) - press * 2.5;
          dy += round * -1.1;
        } else {
          dy = jawDrop * (15 + 20 * s * (1 - cornerFactor * 0.3));
          dy += round * s * 1.6;
          dy -= press * s * 2;
          dy -= bite * s * 3.8;
        }
        dy *= (0.4 + 0.6 * (1 - cornerFactor * 0.7));
      } else if (ring === 1) {
        if (isUpper) dy = -jawDrop * (1.1 + 1.8 * (1 - cornerFactor)) - press * 1.6;
        else dy = jawDrop * (10 + 13 * s) * 0.76 - press * s * 1.3 - bite * s * 2;
        dy *= (0.5 + 0.5 * (1 - cornerFactor * 0.5));
      } else if (ring === 2) {
        if (s > 0) dy = jawDrop * (5 * s) * 0.6;
        else dy = -jawDrop * 0.7 * (1 - cornerFactor) * 0.4;
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
  const mx = (destination[i] + destination[j] + destination[k]) / 3;
  const my = (destination[i + 1] + destination[j + 1] + destination[k + 1]) / 3;
  context.save();
  context.beginPath();
  [i, j, k].forEach((index, n) => {
    const x = destination[index], y = destination[index + 1];
    const length = Math.hypot(x - mx, y - my) || 1;
    const px = x + (x - mx) / length * 0.55, py = y + (y - my) / length * 0.55;
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
    try { this.context = this.canvas?.getContext?.("2d"); } catch {}
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
      this.innerSource[i * 2] = 90 + 55 * Math.cos(angle);
      this.innerSource[i * 2 + 1] = 30 + (s < 0 ? 15 : 18) * s;
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
    // Masque radial doux + feather horizontal
    const grad = context.createRadialGradient(CX, CY, 0, CX, CY, Math.max(width, height) * 0.52);
    grad.addColorStop(0, "black");
    grad.addColorStop(0.55, "black");
    grad.addColorStop(0.78, "rgba(0,0,0,0.6)");
    grad.addColorStop(0.92, "rgba(0,0,0,0.12)");
    grad.addColorStop(1, "transparent");
    context.fillStyle = grad;
    context.fillRect(0, 0, width, height);
    context.globalCompositeOperation = "destination-in";
    const hGrad = context.createLinearGradient(0, 0, width, 0);
    hGrad.addColorStop(0, "transparent");
    hGrad.addColorStop(0.055, "rgba(0,0,0,0.6)");
    hGrad.addColorStop(0.16, "black");
    hGrad.addColorStop(0.84, "black");
    hGrad.addColorStop(0.945, "rgba(0,0,0,0.6)");
    hGrad.addColorStop(1, "transparent");
    context.fillStyle = hGrad;
    context.fillRect(0, 0, width, height);
  }

  prepare() {
    if (!this.context || this.destroyed || !this.image.complete || !this.image.naturalWidth) return;
    if (this.image.naturalWidth !== PORTRAIT_SIZE.width || this.image.naturalHeight !== PORTRAIT_SIZE.height) {
      this.state = "unavailable"; return;
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
    const key = keys.map(name => this.pose[name].toFixed(4)).join("/");
    if (key === this.lastKey) return;
    this.lastKey = key;
    const idle = this.pose.open < 0.005 && this.pose.round < 0.005 && this.pose.wide < 0.005 && this.pose.press < 0.01 && this.pose.bite < 0.01;
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
      context.fillStyle = "#0a1204";
      context.beginPath();
      for (let i = 0; i < COUNT; i++) context.lineTo(this.destination[i * 2], this.destination[i * 2 + 1]);
      context.closePath(); context.fill();
    }
    for (const indices of MESH.triangles) triangle(context, this.base, MESH.vertices, this.destination, indices);
    context.globalCompositeOperation = "destination-in";
    context.drawImage(this.mask, 0, 0);
    context.globalCompositeOperation = "source-over";
    // Ombre naturelle
    if (this.pose.open > 0.08) {
      context.save();
      context.globalCompositeOperation = "multiply";
      context.fillStyle = `rgba(0,0,0,${0.05 + this.pose.open * 0.09})`;
      context.beginPath();
      context.ellipse(CX, CY + 18 + this.pose.open * 12, 32 + this.pose.wide * 8, 4 + this.pose.open * 3, 0, 0, Math.PI * 2);
      context.fill();
      context.restore();
    }
    // Lueur verte subtile
    if (this.pose.open > 0.04) {
      context.save();
      context.globalCompositeOperation = "screen";
      context.fillStyle = `rgba(95, 191, 23, ${0.012 + this.pose.open * 0.02})`;
      context.beginPath();
      context.ellipse(CX, CY, 42 + this.pose.wide * 5, 18 + this.pose.open * 8, 0, 0, Math.PI * 2);
      context.fill();
      context.restore();
    }
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
