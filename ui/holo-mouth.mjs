// KIRA - Bouche holographique naturelle et réaliste
// Rendu humain: pas une photo qui s'étire, mais une vraie articulation labiale
// Mesures avatar 1024x1024: bouche centrée (510, 567), coins 444->576, lèvres 548->595
// Nouvelle approche: maillage anatomique + intérieur procédural réaliste
import * as THREE from "three";
import { LipMotion, REST_MOUTH } from "./lips.mjs";

const PORTRAIT_W = 1024;
const PORTRAIT_H = 1024;
// Fenêtre autour de la bouche - légèrement agrandie pour inclure menton et joues
const REGION = { x: 400, y: 515, width: 220, height: 110 };
// Centre de la fente labiale dans la fenêtre
const CX = 110; // 510 - 400
const CY = 52;  // 567 - 515
const COUNT = 48; // Plus de points = contour plus lisse
const RINGS = 5;  // 0: bord interne lèvres, 1: bord externe lèvres, 2: péri-oral, 3: mâchoire, 4: lointain fixe
const bounded = n => Math.min(1, Math.max(0, Number.isFinite(n) ? n : 0));

// Courbe de lèvre supérieure (cupid's bow subtil) et inférieure plus charnue
function createMesh() {
  const vertices = new Float32Array(COUNT * RINGS * 2);
  const triangles = [];
  for (let ring = 0; ring < RINGS; ring++) {
    for (let i = 0; i < COUNT; i++) {
      const angle = (i / COUNT) * Math.PI * 2;
      const c = Math.cos(angle);
      const s = Math.sin(angle);
      let x, y;
      // Forme de bouche au repos: plus large que haute, avec légère courbe
      if (ring === 0) {
        // Bord interne - fente labiale fermée
        const cupid = Math.cos(2 * angle) * 0.8; // léger arc de Cupidon en haut
        const upperBias = s < 0 ? 1 : 0;
        x = CX + 36 * c;
        y = CY + cupid * 0.6 + (s < 0 ? 1.2 * s : 1.8 * s) + upperBias * Math.exp(-(c*c)/0.08) * 0.5;
      } else if (ring === 1) {
        // Bord externe lèvres - épaisseur des lèvres
        const lipThicknessUpper = 9 + 3 * Math.exp(-(c*c)/0.15); // plus épais au centre
        const lipThicknessLower = 13;
        x = CX + 50 * c;
        y = CY + (s < 0 ? lipThicknessUpper * s + 3 * Math.exp(-((c/0.22)**2)) : lipThicknessLower * s);
      } else if (ring === 2) {
        // Zone péri-orale - peau autour des lèvres
        x = CX + 72 * c;
        y = CY + (s < 0 ? 28 * s : 42 * s) + (s < 0 ? 4 * Math.exp(-((c/0.28)**2)) : 0);
      } else if (ring === 3) {
        // Mâchoire et joues - suit le mouvement de la mâchoire
        x = CX + 96 * c;
        y = CY + (s < 0 ? 38 * s : 62 * s);
      } else {
        // Lointain - ancrage fixe sur les bords de la fenêtre
        const dx = Math.abs(c) < 1e-6 ? Infinity : (c > 0 ? REGION.width - CX : -CX) / c;
        const dy = Math.abs(s) < 1e-6 ? Infinity : (s > 0 ? REGION.height - CY : -CY) / s;
        const distance = Math.min(dx, dy) * 0.98; // légère marge
        x = CX + distance * c;
        y = CY + distance * s;
      }
      const idx = (ring * COUNT + i) * 2;
      vertices[idx] = x;
      vertices[idx + 1] = y;
      if (ring < RINGS - 1) {
        const a = ring * COUNT + i;
        const b = ring * COUNT + (i + 1) % COUNT;
        const d = a + COUNT;
        const e = b + COUNT;
        triangles.push([a, b, d], [b, e, d]);
      }
    }
  }
  return { vertices, triangles };
}
const MESH = createMesh();

// Déformation anatomiquement correcte
// - Lèvre supérieure: bouge peu verticalement, surtout avec press/bite
// - Lèvre inférieure: suit la mâchoire (open) + mouvements de lèvres
// - Coins: s'étirent avec wide, se resserrent avec round
// - Menton: descend avec open
// - Joues: léger mouvement
export function deformMouth(pose, output = new Float32Array(MESH.vertices.length)) {
  const open = bounded(pose.open);
  const round = bounded(pose.round);
  const wide = bounded(pose.wide);
  const press = bounded(pose.press);
  const bite = bounded(pose.bite);

  // Courbes naturelles
  const jawDrop = open * (0.88 + 0.12 * Math.sin(open * Math.PI * 0.5)); // mâchoire avec easing
  const lipStretch = wide * 0.85 - round * 0.55;

  for (let ring = 0; ring < RINGS; ring++) {
    for (let i = 0; i < COUNT; i++) {
      const idx = (ring * COUNT + i) * 2;
      const x0 = MESH.vertices[idx];
      const y0 = MESH.vertices[idx + 1];
      const angle = (i / COUNT) * Math.PI * 2;
      const s = Math.sin(angle);
      const c = Math.cos(angle);
      const isUpper = s < 0;
      const isLower = s >= 0;
      const isCorner = Math.abs(c) > 0.7;
      const cornerFactor = Math.abs(c); // 0 centre, 1 coins

      // Influence selon l'anneau: centre bouge beaucoup, bords peu
      const influence = [1, 0.92, 0.42, 0.22, 0][ring];

      // === Déformation horizontale (largeur) ===
      // Les coins s'étirent, le centre reste stable
      let xDeform = 0;
      if (ring <= 2) {
        // Étirement naturel: coins bougent plus que centre
        const wideEffect = lipStretch * (0.3 + 0.7 * cornerFactor) * 18 * influence;
        const roundEffect = -round * cornerFactor * 14 * influence;
        xDeform = wideEffect + roundEffect;
        // Press resserre légèrement
        xDeform -= press * cornerFactor * 3 * influence;
      }
      output[idx] = CX + (x0 - CX) * (1 + xDeform * 0.01) + xDeform * 0.15;

      // === Déformation verticale (ouverture) ===
      let yDeform = 0;
      if (ring === 0) {
        // Bord interne: séparation des lèvres
        if (isUpper) {
          // Lèvre supérieure: monte légèrement, surtout avec open fort
          yDeform = -jawDrop * (2.5 + 3.5 * (1 - cornerFactor)) - press * 2.2;
          yDeform += round * -1.2;
          // Bite: lèvre supérieure légèrement abaissée par dents
          if (isLower) yDeform -= bite * 2;
        } else {
          // Lèvre inférieure: descend beaucoup avec mâchoire
          yDeform = jawDrop * (14 + 18 * s * (1 - cornerFactor * 0.3));
          yDeform += round * s * 1.5;
          yDeform -= press * s * 1.8;
          yDeform -= bite * s * 3.5; // dents tirent lèvre inférieure vers haut
        }
        // Coins restent plus stables verticalement
        yDeform *= (0.4 + 0.6 * (1 - cornerFactor * 0.7));
      } else if (ring === 1) {
        // Bord externe lèvres
        if (isUpper) {
          yDeform = -jawDrop * (1.2 + 1.8 * (1 - cornerFactor)) - press * 1.5;
        } else {
          yDeform = jawDrop * (9 + 12 * s) * 0.75;
          yDeform -= press * s * 1.2;
          yDeform -= bite * s * 1.8;
        }
        yDeform *= (0.5 + 0.5 * (1 - cornerFactor * 0.5));
      } else if (ring === 2) {
        // Péri-oral: joues et peau autour
        if (isLower) {
          yDeform = jawDrop * (4.5 * s) * 0.6;
        } else {
          yDeform = -jawDrop * 0.8 * (1 - cornerFactor) * 0.4;
        }
      } else if (ring === 3) {
        // Mâchoire: suit la mâchoire
        if (isLower) {
          yDeform = jawDrop * (7 * s) * 0.5;
        }
      }
      // Anneau 4 = fixe

      output[idx + 1] = y0 + yDeform;
    }
  }
  return output;
}

function triangle(ctx, texture, source, dest, indices) {
  const [i, j, k] = indices.map(n => n * 2);
  const sx = source[i], sy = source[i + 1];
  const dx = dest[i], dy = dest[i + 1];
  const ux = source[j] - sx, uy = source[j + 1] - sy;
  const vx = source[k] - sx, vy = source[k + 1] - sy;
  const dux = dest[j] - dx, duy = dest[j + 1] - dy;
  const dvx = dest[k] - dx, dvy = dest[k + 1] - dy;
  const det = ux * vy - uy * vx;
  if (Math.abs(det) < 0.0001 || Math.abs(dux * dvy - duy * dvx) < 0.00001) return;
  const a = (dux * vy - dvx * uy) / det;
  const b = (duy * vy - dvy * uy) / det;
  const c_ = (dvx * ux - dux * vx) / det;
  const d = (dvy * ux - duy * vx) / det;
  // Overlap anti-alias
  const mx = (dest[i] + dest[j] + dest[k]) / 3;
  const my = (dest[i + 1] + dest[j + 1] + dest[k + 1]) / 3;
  ctx.save();
  ctx.beginPath();
  [i, j, k].forEach((index, n) => {
    const x = dest[index], y = dest[index + 1];
    const len = Math.hypot(x - mx, y - my) || 1;
    const px = x + (x - mx) / len * 0.55, py = y + (y - my) / len * 0.55;
    if (n) ctx.lineTo(px, py); else ctx.moveTo(px, py);
  });
  ctx.closePath();
  ctx.clip();
  ctx.setTransform(a, b, c_, d, dx - a * sx - c_ * sy, dy - b * sx - d * sy);
  ctx.drawImage(texture, 0, 0);
  ctx.restore();
}

export class HoloMouth {
  constructor(image, three, scene, plane) {
    this.three = three;
    this.scene = scene;
    this.motion = new LipMotion();
    this.destroyed = false;
    this.ready = false;
    this.lastKey = "";
    this.pose = { ...REST_MOUTH };
    if (!image || !image.naturalWidth || image.naturalWidth !== PORTRAIT_W) return;

    const W = REGION.width, H = REGION.height;
    // Patch peau - zone autour de la bouche
    this.patch = document.createElement("canvas");
    this.patch.width = W; this.patch.height = H;
    this.patch.getContext("2d", { willReadFrequently: true }).drawImage(image, REGION.x, REGION.y, W, H, 0, 0, W, H);

    // Masque avec feather elliptique doux - évite les bords durs
    this.mask = document.createElement("canvas");
    this.mask.width = W; this.mask.height = H;
    const mctx = this.mask.getContext("2d");
    // Masque elliptique avec dégradé doux
    const gradient = mctx.createRadialGradient(CX, CY, 0, CX, CY, Math.max(W, H) * 0.52);
    gradient.addColorStop(0, "black");
    gradient.addColorStop(0.55, "black");
    gradient.addColorStop(0.78, "rgba(0,0,0,0.65)");
    gradient.addColorStop(0.92, "rgba(0,0,0,0.15)");
    gradient.addColorStop(1, "transparent");
    mctx.fillStyle = gradient;
    mctx.fillRect(0, 0, W, H);
    // Adoucissement horizontal supplémentaire pour les coins
    mctx.globalCompositeOperation = "destination-in";
    const hGrad = mctx.createLinearGradient(0, 0, W, 0);
    hGrad.addColorStop(0, "transparent");
    hGrad.addColorStop(0.08, "rgba(0,0,0,0.6)");
    hGrad.addColorStop(0.18, "black");
    hGrad.addColorStop(0.82, "black");
    hGrad.addColorStop(0.92, "rgba(0,0,0,0.6)");
    hGrad.addColorStop(1, "transparent");
    mctx.fillStyle = hGrad;
    mctx.fillRect(0, 0, W, H);

    // Canvas de rendu final
    this.canvas = document.createElement("canvas");
    this.canvas.width = W; this.canvas.height = H;
    this.context = this.canvas.getContext("2d", { willReadFrequently: true });
    this.destination = new Float32Array(MESH.vertices.length);

    // === Intérieur de bouche RÉALISTE ===
    this.interior = document.createElement("canvas");
    this.interior.width = 200; this.interior.height = 90;
    const ictx = this.interior.getContext("2d");
    // Cavité buccale sombre avec profondeur
    const cavityGrad = ictx.createRadialGradient(100, 45, 0, 100, 55, 85);
    cavityGrad.addColorStop(0, "#1a0f08");
    cavityGrad.addColorStop(0.25, "#0f0804");
    cavityGrad.addColorStop(0.55, "#080401");
    cavityGrad.addColorStop(1, "#020100");
    ictx.fillStyle = cavityGrad;
    ictx.fillRect(0, 0, 200, 90);

    // Langue - forme naturelle rosée en bas
    ictx.fillStyle = "#3a1a12";
    ictx.beginPath();
    ictx.ellipse(100, 68, 38, 14, 0, 0, Math.PI * 2);
    ictx.fill();
    ictx.fillStyle = "#5a2a1e";
    ictx.beginPath();
    ictx.ellipse(100, 66, 30, 9, 0, 0, Math.PI * 2);
    ictx.fill();
    // Reflet langue
    ictx.fillStyle = "rgba(120, 60, 50, 0.25)";
    ictx.beginPath();
    ictx.ellipse(100, 62, 18, 4, 0, 0, Math.PI * 2);
    ictx.fill();

    // Dents supérieures - rangée réaliste
    ictx.fillStyle = "#e8ddd0";
    ictx.fillRect(52, 8, 96, 3);
    // Dents individuelles subtiles
    ictx.fillStyle = "#d8cec0";
    for (let tx = 54; tx < 146; tx += 12) {
      ictx.fillRect(tx, 8, 1, 11);
    }
    // Dents supérieures - corps
    const upperTeethGrad = ictx.createLinearGradient(0, 8, 0, 22);
    upperTeethGrad.addColorStop(0, "#f5efe6");
    upperTeethGrad.addColorStop(0.4, "#e8ddd0");
    upperTeethGrad.addColorStop(1, "#c8b8a0");
    ictx.fillStyle = upperTeethGrad;
    ictx.beginPath();
    ictx.roundRect(52, 11, 96, 12, [0, 0, 3, 3]);
    ictx.fill();

    // Dents inférieures - moins visibles, seulement quand bouche très ouverte
    ictx.fillStyle = "#d0c4b4";
    ictx.fillRect(62, 72, 76, 2);

    // Ombres internes pour profondeur
    ictx.fillStyle = "rgba(0,0,0,0.35)";
    ictx.beginPath();
    ictx.ellipse(100, 45, 62, 28, 0, 0, Math.PI * 2);
    ictx.fill();

    // Lueur verte subtile (thème #5FBF17) - très discrète
    ictx.fillStyle = "rgba(95, 191, 23, 0.04)";
    ictx.beginPath();
    ictx.ellipse(100, 45, 70, 32, 0, 0, Math.PI * 2);
    ictx.fill();

    this.interiorReady = true;

    // Sources pour intérieur
    this.innerSource = new Float32Array((COUNT + 1) * 2);
    this.innerDestination = new Float32Array(this.innerSource.length);
    for (let i = 0; i < COUNT; i++) {
      const angle = (i / COUNT) * Math.PI * 2;
      const s = Math.sin(angle);
      // Forme intérieure ovale naturelle
      this.innerSource[i * 2] = 100 + 58 * Math.cos(angle) * (0.9 + 0.1 * Math.cos(angle * 2));
      this.innerSource[i * 2 + 1] = 42 + (s < 0 ? 16 : 22) * s;
    }
    this.innerSource[COUNT * 2] = 100;
    this.innerSource[COUNT * 2 + 1] = 42;

    // Plan Three.js
    const planeW = (plane.geometry && plane.geometry.parameters && plane.geometry.parameters.width) || 6.4;
    const planeH = (plane.geometry && plane.geometry.parameters && plane.geometry.parameters.height) || 6.4;
    const geometry = new three.PlaneGeometry(W / PORTRAIT_W * planeW, H / PORTRAIT_H * planeH);
    this.texture = new three.CanvasTexture(this.canvas);
    this.texture.minFilter = three.LinearFilter;
    this.texture.magFilter = three.LinearFilter;
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
      plane.position.z + 0.015
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
    const key = keys.map(n => this.pose[n].toFixed(4)).join("/");
    if (key === this.lastKey) return;
    this.lastKey = key;
    const ctx = this.context;
    const isIdle = this.pose.open < 0.005 && this.pose.round < 0.005 && this.pose.wide < 0.005 && this.pose.press < 0.01 && this.pose.bite < 0.01;

    if (isIdle) {
      ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      this.texture.needsUpdate = true;
      return;
    }

    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    deformMouth(this.pose, this.destination);

    // Calcul centre bouche pour intérieur
    this.innerDestination.set(this.destination.subarray(0, COUNT * 2));
    let cx = 0, cy = 0;
    for (let i = 0; i < COUNT; i++) { cx += this.destination[i * 2]; cy += this.destination[i * 2 + 1]; }
    this.innerDestination[COUNT * 2] = cx / COUNT;
    this.innerDestination[COUNT * 2 + 1] = cy / COUNT;

    // 1. Intérieur bouche (cavité, langue, dents) - seulement si ouvert
    if (this.pose.open > 0.03) {
      // Clip intérieur pour forme bouche
      ctx.save();
      ctx.beginPath();
      for (let i = 0; i < COUNT; i++) {
        const x = this.destination[i * 2], y = this.destination[i * 2 + 1];
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.clip();

      // Fond cavité
      for (let i = 0; i < COUNT; i++) {
        triangle(ctx, this.interior, this.innerSource, this.innerDestination, [COUNT, i, (i + 1) % COUNT]);
      }

      // Dents supérieures visibles selon ouverture
      if (this.pose.open > 0.08) {
        const teethAlpha = Math.min(1, (this.pose.open - 0.08) / 0.18);
        ctx.globalAlpha = teethAlpha;
        // Dents déjà dans interior, mais on ajoute reflet
        ctx.fillStyle = `rgba(245, 240, 230, ${0.15 * teethAlpha})`;
        ctx.fillRect(this.innerDestination[COUNT * 2] - 38, this.innerDestination[COUNT * 2 + 1] - 18, 76, 2);
        ctx.globalAlpha = 1;
      }

      ctx.restore();
    }

    // 2. Peau et lèvres déformées - maillage photo
    for (const tri of MESH.triangles) {
      triangle(ctx, this.patch, MESH.vertices, this.destination, tri);
    }

    // 3. Ombre sous lèvre inférieure pour profondeur (naturel)
    if (this.pose.open > 0.1) {
      ctx.save();
      ctx.globalCompositeOperation = "multiply";
      ctx.fillStyle = `rgba(0, 0, 0, ${0.08 + this.pose.open * 0.12})`;
      ctx.beginPath();
      // Ombre sous lèvre inférieure
      const lipBottomY = cy / COUNT + this.pose.open * 18;
      ctx.ellipse(CX, lipBottomY + 6, 32 + this.pose.wide * 8, 4 + this.pose.open * 3, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // 4. Masque feather pour bords doux
    ctx.globalCompositeOperation = "destination-in";
    ctx.drawImage(this.mask, 0, 0);
    ctx.globalCompositeOperation = "source-over";

    // 5. Légère lueur verte thème (très subtile)
    if (this.pose.open > 0.05) {
      ctx.save();
      ctx.globalCompositeOperation = "screen";
      ctx.fillStyle = `rgba(95, 191, 23, ${0.02 + this.pose.open * 0.03})`;
      ctx.beginPath();
      ctx.ellipse(CX, CY, 45 + this.pose.wide * 5, 18 + this.pose.open * 8, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

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
