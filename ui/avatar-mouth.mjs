// Rendu des lèvres sur l'avatar Three.js (portrait 1024×1024).
// Adapté du système mouth.mjs (maillage + visèmes) aux mesures réelles de
// l'avatar actuel : bouche centrée à (532, 587), coins ±67 px, seam y=587.
// La synchronisation vient de l'horloge audio réelle (speech.mjs) : aucun
// décalage entre le son et les lèvres.
import * as THREE from "three";
import { LipMotion, REST_MOUTH } from "./lips.mjs";

const PORTRAIT_W = 1024;
const PORTRAIT_H = 1024;
// Fenêtre prélevée sur le portrait (autour de la bouche, bords fixes).
const REGION = { x: 432, y: 542, width: 200, height: 120 };
// Centre de la fente labiale dans le repère de la fenêtre.
const CX = 100; // 532 - 432
const CY = 45;  // 587 - 542
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
        x = CX + 40 * c;
        y = CY - Math.cos(2 * angle) * 1.7 + (s < 0 ? 1.5 : 1.7) * s;
      } else if (ring === 1) {
        x = CX + 52 * c;
        y = CY + (s < 0 ? 17 : 20) * s + (s < 0 ? 5 * Math.exp(-((c / 0.2) ** 2)) : 0);
      } else if (ring === 2) {
        x = CX + 78 * c;
        y = CY + (s < 0 ? 30 : 48) * s;
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
      const influence = [1, 0.96, 0.25, 0][ring];
      output[index] = CX + (x - CX) * (1 + (wide * 0.12 - round * 0.34 - press * 0.012) * influence);
      let dy = 0;
      if (ring <= 1) {
        dy = open * (s >= 0 ? 2.4 + 22 * s : (ring === 0 ? 8 : 4.8) * s + 2.4 * c * c);
        dy += round * s * 1.6;
        if (ring === 0) {
          const seam = CY - Math.cos(2 * angle) * 1.7;
          dy += press * (seam + s * 0.12 - y);
          if (s > 0) dy -= bite * Math.min(5.5, open * 18) * s;
        } else {
          dy -= press * s * 1.3;
          if (s > 0) dy -= bite * s * 1.6;
        }
      } else if (ring === 2) {
        dy = open * (s > 0 ? 7 : 1.2) * s;
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

const INTERIOR_SIZE = { width: 180, height: 62 };

export class AvatarMouth {
  // image : l'élément <img> de la texture de l'avatar (1024×1024).
  // three : l'objet THREE ; scene : la scène où ajouter le plan superposé.
  // plane : le plan de l'avatar (pour copier position/échelle exactement).
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
    vertical.addColorStop(0, "transparent"); vertical.addColorStop(0.08, "black");
    vertical.addColorStop(0.88, "black"); vertical.addColorStop(1, "transparent");
    maskContext.fillStyle = vertical; maskContext.fillRect(0, 0, W, H);

    this.canvas = document.createElement("canvas");
    this.canvas.width = W; this.canvas.height = H;
    this.context = this.canvas.getContext("2d");
    this.destination = new Float32Array(MESH.vertices.length);
    this.innerSource = new Float32Array((COUNT + 1) * 2);
    this.innerDestination = new Float32Array(this.innerSource.length);
    for (let i = 0; i < COUNT; i++) {
      const angle = i / COUNT * Math.PI * 2, s = Math.sin(angle);
      this.innerSource[i * 2] = 90 + 55 * Math.cos(angle);
      this.innerSource[i * 2 + 1] = 30 + (s < 0 ? 15 : 18) * s;
    }
    this.innerSource[COUNT * 2] = 90; this.innerSource[COUNT * 2 + 1] = 30;

    // Intérieur de la bouche (dents photo) — chargement tolérant.
    this.interior = new Image();
    this.interior.onload = () => { this.interiorReady = true; this.lastKey = ""; };
    this.interior.src = "assets/kira-mouth-interior.webp";

    // Plan Three.js superposé exactement sur la bouche de l'avatar.
    const geometry = new three.PlaneGeometry(W / PORTRAIT_W * plane.scale.x, H / PORTRAIT_H * plane.scale.y);
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
      plane.position.x + centerX * plane.scale.x,
      plane.position.y + centerY * plane.scale.y,
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
    if (this.interiorReady) {
      for (let i = 0; i < COUNT; i++) triangle(context, this.interior, this.innerSource, this.innerDestination, [COUNT, i, (i + 1) % COUNT]);
    } else {
      context.fillStyle = "#2b1013"; context.beginPath();
      for (let i = 0; i < COUNT; i++) context.lineTo(this.destination[i * 2], this.destination[i * 2 + 1]);
      context.closePath(); context.fill();
    }
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
