// Animation des lèvres de l'hologramme KIRA (portrait 1024×1024).
// Mesures réelles de l'avatar MATRIX actuel : bouche centrée à (510, 567),
// coins x444→576, lèvres y548→595. Maillage visème (lips.mjs) synchronisé
// sur l'horloge audio réelle (speech.mjs) — aucun décalage.
import * as THREE from "three";
import { LipMotion, REST_MOUTH } from "./lips.mjs";

const PORTRAIT_W = 1024;
const PORTRAIT_H = 1024;
// Fenêtre prélevée sur le portrait (autour de la bouche, bords fixes).
const REGION = { x: 415, y: 528, width: 190, height: 88 };
// Centre de la fente labiale dans le repère de la fenêtre.
const CX = 95;  // 510 - 415
const CY = 39;  // 567 - 528
const COUNT = 32;
const bounded = n => Math.min(1, Math.max(0, Number.isFinite(n) ? n : 0));

function createMesh() {
  const vertices = new Float32Array(COUNT * 4 * 2);
  const triangles = [];
  for (let ring = 0; ring < 4; ring++) {
    for (let i = 0; i < COUNT; i++) {
      const angle = i / COUNT * Math.PI * 2;
      const c = Math.cos(angle), s = Math.sin(angle);
      let x, y;
      if (ring === 0) {
        x = CX + 34 * c;
        y = CY - Math.cos(2 * angle) * 1.6 + (s < 0 ? 1.4 : 1.6) * s;
      } else if (ring === 1) {
        x = CX + 45 * c;
        y = CY + (s < 0 ? 14 : 17) * s + (s < 0 ? 4 * Math.exp(-((c / 0.2) ** 2)) : 0);
      } else if (ring === 2) {
        x = CX + 66 * c;
        y = CY + (s < 0 ? 25 : 40) * s;
      } else {
        const dx = Math.abs(c) < 1e-6 ? Infinity : (c > 0 ? REGION.width - CX : -CX) / c;
        const dy = Math.abs(s) < 1e-6 ? Infinity : (s > 0 ? REGION.height - CY : -CY) / s;
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
const MESH = createMesh();

export function deformMouth(pose, output = new Float32Array(MESH.vertices.length)) {
  const open = bounded(pose.open), round = bounded(pose.round), wide = bounded(pose.wide);
  const press = bounded(pose.press), bite = bounded(pose.bite);
  for (let ring = 0; ring < 4; ring++) {
    for (let i = 0; i < COUNT; i++) {
      const index = (ring * COUNT + i) * 2;
      const x = MESH.vertices[index], y = MESH.vertices[index + 1];
      const angle = i / COUNT * Math.PI * 2;
      const s = Math.sin(angle), c = Math.cos(angle);
      const influence = [1, 0.96, 0.5, 0][ring];
      output[index] = CX + (x - CX) * (1 + (wide * 0.2 - round * 0.42 - press * 0.012) * influence);
      let dy = 0;
      if (ring <= 1) {
        // Ouverture ample et humaine : lèvre inférieure qui descend, supérieure
        // qui se lève, commissures entraînées — toute la bouche articule.
        dy = open * (s >= 0
          ? (ring === 0 ? 3 + 24 * s : 4 + 30 * s)
          : (ring === 0 ? 11 : 6.5) * s + (ring === 0 ? 3 : 2.4) * c * c);
        dy += round * s * 2.2;
        if (ring === 0) {
          const seam = CY - Math.cos(2 * angle) * 1.6;
          dy += press * (seam + s * 0.1 - y);
          if (s > 0) dy -= bite * Math.min(5.4, open * 22) * s;
        } else {
          dy -= press * s * 1.1;
          if (s > 0) dy -= bite * s * 1.6;
        }
      } else if (ring === 2) {
        // Menton et joues suivent la mâchoire (mouvement complet du bas du visage).
        dy = open * (s > 0 ? 11 * s : 2.4 * s);
      }
      output[index + 1] = y + dy;
    }
  }
  return output;
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
    const px = x + (x - mx) / length * 0.45, py = y + (y - my) / length * 0.45;
    if (n) context.lineTo(px, py); else context.moveTo(px, py);
  });
  context.closePath();
  context.clip();
  context.setTransform(a, b, c, d, dx - a * sx - c * sy, dy - b * sx - d * sy);
  context.drawImage(texture, 0, 0);
  context.restore();
}

export class HoloMouth {
  // image : l'élément <img> de la texture de l'hologramme (1024×1024).
  constructor(image, three, scene, plane) {
    this.three = three;
    this.scene = scene;
    this.motion = new LipMotion();
    this.destroyed = false;
    this.ready = false;
    this.interiorReady = false;
    this.lastKey = "";
    this.pose = { ...REST_MOUTH };
    if (!image || !image.naturalWidth || image.naturalWidth !== PORTRAIT_W) return;

    const W = REGION.width, H = REGION.height;
    this.patch = document.createElement("canvas");
    this.patch.width = W; this.patch.height = H;
    this.patch.getContext("2d").drawImage(image, REGION.x, REGION.y, W, H, 0, 0, W, H);

    this.mask = document.createElement("canvas");
    this.mask.width = W; this.mask.height = H;
    const maskContext = this.mask.getContext("2d");
    const horizontal = maskContext.createLinearGradient(0, 0, W, 0);
    horizontal.addColorStop(0, "transparent"); horizontal.addColorStop(0.06, "black");
    horizontal.addColorStop(0.94, "black"); horizontal.addColorStop(1, "transparent");
    maskContext.fillStyle = horizontal; maskContext.fillRect(0, 0, W, H);
    maskContext.globalCompositeOperation = "destination-in";
    const vertical = maskContext.createLinearGradient(0, 0, 0, H);
    vertical.addColorStop(0, "transparent"); vertical.addColorStop(0.09, "black");
    vertical.addColorStop(0.88, "black"); vertical.addColorStop(1, "transparent");
    maskContext.fillStyle = vertical; maskContext.fillRect(0, 0, W, H);

    this.canvas = document.createElement("canvas");
    this.canvas.width = W; this.canvas.height = H;
    this.context = this.canvas.getContext("2d");
    this.destination = new Float32Array(MESH.vertices.length);

    // Intérieur de la bouche : teinte holographique sombre dorée.
    this.interior = document.createElement("canvas");
    this.interior.width = 180; this.interior.height = 62;
    const interiorContext = this.interior.getContext("2d");
    // Intérieur lumineux : dans un hologramme MATRIX, la bouche ouverte rayonne.
    const gradient = interiorContext.createLinearGradient(0, 0, 0, 62);
    gradient.addColorStop(0, "#aaff9c");
    gradient.addColorStop(0.45, "#1d8a2c");
    gradient.addColorStop(1, "#06310f");
    interiorContext.fillStyle = gradient;
    interiorContext.fillRect(0, 0, 180, 62);
    const mouthGlow = interiorContext.createRadialGradient(90, 24, 4, 90, 24, 58);
    mouthGlow.addColorStop(0, "rgba(130, 255, 150, 0.95)");
    mouthGlow.addColorStop(1, "rgba(130, 255, 150, 0)");
    interiorContext.fillStyle = mouthGlow;
    interiorContext.fillRect(0, 0, 180, 62);
    // Lignes de balayage cohérentes avec la projection.
    interiorContext.fillStyle = "rgba(4, 40, 12, 0.25)";
    for (let ly = 3; ly < 62; ly += 6) interiorContext.fillRect(0, ly, 180, 2);
    this.interiorReady = true;

    this.canvas2texture = null;
    this.destination = new Float32Array(MESH.vertices.length);
    this.innerSource = new Float32Array((COUNT + 1) * 2);
    this.innerDestination = new Float32Array(this.innerSource.length);
    for (let i = 0; i < COUNT; i++) {
      const angle = i / COUNT * Math.PI * 2, s = Math.sin(angle);
      this.innerSource[i * 2] = 90 + 55 * Math.cos(angle);
      this.innerSource[i * 2 + 1] = 30 + (s < 0 ? 15 : 18) * s;
    }
    this.innerSource[COUNT * 2] = 90; this.innerSource[COUNT * 2 + 1] = 30;

    // Plan Three.js superposé exactement sur la bouche de l'hologramme.
    // Taille RÉELLE du plan avatar (geometry.parameters) — mesh.scale reste à 1.
    const planeW = (plane.geometry && plane.geometry.parameters && plane.geometry.parameters.width) || 6.4;
    const planeH = (plane.geometry && plane.geometry.parameters && plane.geometry.parameters.height) || 6.4;
    const geometry = new three.PlaneGeometry(W / PORTRAIT_W * planeW, H / PORTRAIT_H * planeH);
    this.texture = new three.CanvasTexture(this.canvas);
    const material = new three.MeshBasicMaterial({
      map: this.texture,
      transparent: true,
      depthWrite: false,
      depthTest: false,
      toneMapped: false,
    });
    this.overlay = new three.Mesh(geometry, material);
    this.overlay.renderOrder = (plane.renderOrder || 0) + 1;
    const centerX = (REGION.x + CX) / PORTRAIT_W - 0.5;
    const centerY = 0.5 - (REGION.y + CY) / PORTRAIT_H;
    this.overlay.position.set(
      plane.position.x + centerX * planeW,
      plane.position.y + centerY * planeH,
      plane.position.z + 0.01
    );
    scene.add(this.overlay);
    this.ready = true;
  }

  update(voice, { now = 0, disabled = false, demo = null } = {}) {
    if (!this.ready || this.destroyed) return null;
    const pose = this.motion.sample(voice, { now, disabled, demo });
    this.render(pose);
    return pose;
  }

  render(pose) {
    if (!this.ready || this.destroyed) return;
    this.pose = { ...pose };
    const keys = ["open", "round", "wide", "bite", "press"];
    for (const key of keys) this.pose[key] = bounded(this.pose[key]);
    const key = keys.map(name => this.pose[name].toFixed(3)).join("/");
    if (key === this.lastKey) return;
    this.lastKey = key;
    const context = this.context;
    const idle = keys.every(name => this.pose[name] < 0.001);
    if (idle) {
      context.clearRect(0, 0, this.canvas.width, this.canvas.height);
      this.texture.needsUpdate = true;
      return;
    }
    context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    deformMouth(this.pose, this.destination);
    this.innerDestination.set(this.destination.subarray(0, COUNT * 2));
    let x = 0, y = 0;
    for (let i = 0; i < COUNT; i++) { x += this.destination[i * 2]; y += this.destination[i * 2 + 1]; }
    this.innerDestination[COUNT * 2] = x / COUNT;
    this.innerDestination[COUNT * 2 + 1] = y / COUNT;
    for (let i = 0; i < COUNT; i++) triangle(context, this.interior, this.innerSource, this.innerDestination, [COUNT, i, (i + 1) % COUNT]);
    for (const indices of MESH.triangles) triangle(context, this.patch, MESH.vertices, this.destination, indices);
    context.globalCompositeOperation = "destination-in";
    context.drawImage(this.mask, 0, 0);
    context.globalCompositeOperation = "source-over";
    this.texture.needsUpdate = true;
  }

  reset() { this.lastKey = ""; this.motion.reset(); if (this.ready) this.render(REST_MOUTH); }

  destroy() {
    if (this.destroyed) return;
    this.destroyed = true;
    this.reset();
    if (this.overlay) {
      this.scene?.remove?.(this.overlay);
      this.overlay.geometry?.dispose?.();
      this.overlay.material?.dispose?.();
    }
    this.texture?.dispose?.();
  }
}
