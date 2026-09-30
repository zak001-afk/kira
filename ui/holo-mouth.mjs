// KIRA — articulation du portrait naturel (avatar-natural.webp).
// Les pixels des lèvres/peau viennent du portrait, sans recoloration verte.
import { LipMotion, REST_MOUTH } from "./lips.mjs";
import { AVATAR_PORTRAIT, createPortraitMaterial } from "./avatar.mjs?v=orig-1";

const PORTRAIT_W = AVATAR_PORTRAIT.width;
const PORTRAIT_H = AVATAR_PORTRAIT.height;
// Mesures du nouveau portrait 1024×1024 : fente (512, 610), coins 436→588,
// lèvre supérieure ≈588, inférieure ≈645. Inclut la peau sous la mâchoire.
export const MOUTH_REGION = Object.freeze({ x: 376, y: 552, width: 272, height: 192 });
const REGION = MOUTH_REGION;
const CX = 512 - REGION.x;
const CY = 610 - REGION.y;
const COUNT = 48; // Plus de points = contour plus lisse
const RINGS = 5;  // 0: bord interne lèvres, 1: bord externe lèvres, 2: péri-oral, 3: mâchoire, 4: lointain fixe
const bounded = n => Math.min(1, Math.max(0, Number.isFinite(n) ? n : 0));

// Courbe de lèvre supérieure (cupid's bow subtil) et inférieure plus charnue
export function createMouthMesh() {
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
        x = CX + 76 * c;
        y = CY + 0.8 * c * c + 1.2 * s;
      } else if (ring === 1) {
        // Bord externe lèvres - épaisseur des lèvres
        const lipThicknessUpper = 22 + 3 * Math.exp(-(((Math.abs(c) - 0.32) / 0.2) ** 2));
        const lipThicknessLower = 35;
        x = CX + 81 * c;
        y = CY + 0.8 * c * c + (s < 0 ? lipThicknessUpper * s + 7 * Math.exp(-((c/0.18)**2)) : lipThicknessLower * s);
      } else if (ring === 2) {
        // Zone péri-orale - peau autour des lèvres
        x = CX + 103 * c;
        y = CY + (s < 0 ? 43 * s : 64 * s);
      } else if (ring === 3) {
        // Mâchoire et joues - suit le mouvement de la mâchoire
        x = CX + 123 * c;
        y = CY + (s < 0 ? 52 * s : 103 * s);
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
const MESH = createMouthMesh();

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
      output[idx] = CX + (x0 - CX) * (1 + xDeform * 0.01);

      // === Déformation verticale (ouverture) ===
      let yDeform = 0;
      if (ring === 0) {
        // Bord interne: séparation des lèvres
        if (isUpper) {
          // Lèvre supérieure: monte légèrement, surtout avec open fort
          yDeform = -jawDrop * (2.5 + 3.5 * (1 - cornerFactor)) + press * 0.9;
          yDeform += round * -1.2;
        } else {
          // Lèvre inférieure: descend beaucoup avec mâchoire
          yDeform = jawDrop * (14 + 18 * s * (1 - cornerFactor * 0.3));
          yDeform += round * s * 1.5;
          yDeform -= press * s * 0.9;
          yDeform -= bite * s * 3.5; // dents tirent lèvre inférieure vers haut
        }
        // Les lèvres se rejoignent aux coins : l'ouverture se referme là
        // au lieu d'étirer une fente rectiligne d'un coin à l'autre.
        yDeform *= Math.pow(Math.abs(s), 0.85) * (1 - 0.85 * cornerFactor ** 3);
      } else if (ring === 1) {
        // Bord externe lèvres
        if (isUpper) {
          yDeform = -jawDrop * (1.2 + 1.8 * (1 - cornerFactor)) + press * 1.5;
        } else {
          yDeform = jawDrop * (9 + 12 * s) * 0.75;
          yDeform -= press * s * 1.2;
          yDeform -= bite * s * 1.8;
        }
        yDeform *= Math.pow(Math.abs(s), 0.85) * (1 - 0.75 * cornerFactor ** 3);
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
    if (!image || image.naturalWidth !== PORTRAIT_W || image.naturalHeight !== PORTRAIT_H) return;

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

    // Plan Three.js
    const planeW = (plane.geometry && plane.geometry.parameters && plane.geometry.parameters.width) || 6.4;
    const planeH = (plane.geometry && plane.geometry.parameters && plane.geometry.parameters.height) || 6.4;
    const geometry = new three.PlaneGeometry(W / PORTRAIT_W * planeW, H / PORTRAIT_H * planeH);
    this.texture = new three.CanvasTexture(this.canvas);
    this.texture.minFilter = three.LinearFilter;
    this.texture.magFilter = three.LinearFilter;
    // Shader partagé avec le visage et uniform de luminosité IDENTIQUE.
    const material = createPortraitMaterial(three, this.texture);
    material.uniforms.brightness = plane.material.uniforms.brightness;
    this.overlay = new three.Mesh(geometry, material);
    this.overlay.renderOrder = (plane.renderOrder || 0) + 1;
    // Le plan est centré sur le RECTANGLE du patch, pas sur la fente des lèvres.
    const centerX = (REGION.x + W / 2) / PORTRAIT_W - 0.5;
    const centerY = 0.5 - (REGION.y + H / 2) / PORTRAIT_H;
    this.overlay.position.set(centerX * planeW, centerY * planeH, 0);
    // Enfant coplanaire : mêmes translation/échelle/projection, sans décalage.
    // L'ordre de rendu et depthTest:false évitent tout z-fighting.
    this.parent = plane;
    this.parent.add(this.overlay);
    this.ready = true;
  }

  update(voice, { now = 0, disabled = false, demo = null } = {}) {
    if (!this.ready || this.destroyed) return null;
    const pose = this.motion.sample(voice, { now, disabled, demo });
    this.render(pose);
    return pose;
  }

  // Intérieur vivant, dessiné sur la géométrie RÉELLE de ce frame : cavité
  // sombre, langue discrète et arc des dents supérieures qui suit la courbe
  // déformée des lèvres. Plus jamais de bande blanche rectiligne étirée sur
  // toute la largeur, ni de fente qui traverse les coins de la bouche.
  drawInterior(ctx, left, top, right, bottom) {
    const width = right - left;
    const height = bottom - top;
    if (width < 4 || height < 3) return;
    const midX = (left + right) / 2;
    const midY = (top + bottom) / 2;

    // 1. Cavité buccale : presque noire, légèrement plus chaude vers le fond.
    const cavity = ctx.createLinearGradient(0, top, 0, bottom);
    cavity.addColorStop(0, "#160a06");
    cavity.addColorStop(0.45, "#0a0402");
    cavity.addColorStop(1, "#030101");
    ctx.fillStyle = cavity;
    ctx.fillRect(left, top, width, height);

    // 2. Langue discrète au fond, visible seulement en vraie ouverture.
    if (this.pose.open > 0.3 && height > 18) {
      const tongue = ctx.createRadialGradient(midX, bottom - height * 0.18, 2, midX, bottom - height * 0.18, width * 0.3);
      tongue.addColorStop(0, "rgba(122, 62, 48, 0.8)");
      tongue.addColorStop(0.55, "rgba(74, 31, 22, 0.5)");
      tongue.addColorStop(1, "rgba(40, 16, 10, 0)");
      ctx.fillStyle = tongue;
      ctx.beginPath();
      ctx.ellipse(midX, bottom - height * 0.2, width * 0.3, height * 0.26, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    // 3. Arc des dents supérieures : échantillonné sur le contour labial
    // déformé de ce frame. Rendu naturel : émail atténué par l'ombre de la
    // cavité, profondeur proportionnelle à l'ouverture réelle, apparition
    // progressive — plus jamais de bandeau blanc clignotant sur les voyelles
    // légères (EE, SS) où l'écart labial est minuscule.
    if (this.pose.open > 0.2 && height > 12) {
      const upper = [], lower = [];
      for (let i = 0; i < COUNT; i++) {
        const x = this.destination[i * 2], y = this.destination[i * 2 + 1];
        (y < CY ? upper : lower).push([x, y]);
      }
      upper.sort((a, b) => a[0] - b[0]);
      lower.sort((a, b) => a[0] - b[0]);
      if (upper.length > 2 && lower.length > 0) {
        const lowerAt = x => {
          let best = lower[0];
          for (const point of lower) {
            if (Math.abs(point[0] - x) < Math.abs(best[0] - x)) best = point;
          }
          return best[1];
        };
        // L'arc plafonne à ~1/4 de la hauteur de la cavité : les dents
        // suggèrent la rangée, elles ne remplissent jamais l'ouverture.
        const maxDepth = Math.min(8, height * 0.24);
        const tops = [], bottoms = [];
        const step = Math.max(1, Math.floor(upper.length / 14));
        for (let k = 0; k < upper.length; k += step) {
          const [x, y] = upper[k];
          const u = Math.min(1, Math.max(0, (x - left) / width));
          const opening = Math.max(0, lowerAt(x) - y);
          const depth = Math.min(maxDepth, opening * 0.42) * (0.3 + 0.7 * Math.sqrt(Math.sin(Math.PI * u)));
          tops.push([x, y + 1.2]);
          bottoms.push([x, y + 1.2 + depth]);
        }
        if (tops.length > 2) {
          ctx.save();
          ctx.beginPath();
          ctx.moveTo(tops[0][0], tops[0][1]);
          for (const [x, y] of tops) ctx.lineTo(x, y);
          for (let k = bottoms.length - 1; k >= 0; k--) ctx.lineTo(bottoms[k][0], bottoms[k][1]);
          ctx.closePath();
          // Apparition douce avec l'ouverture : rien de blanc en articulation
          // légère, émail discret en pleine ouverture.
          ctx.globalAlpha = 0.35 + 0.45 * Math.min(1, (this.pose.open - 0.2) / 0.5);
          const teeth = ctx.createLinearGradient(0, top, 0, top + maxDepth + 4);
          teeth.addColorStop(0, "#d9cdb8");
          teeth.addColorStop(0.5, "#b7a687");
          teeth.addColorStop(1, "#7d6849");
          ctx.fillStyle = teeth;
          ctx.fill();
          // La base de l'arc fond dans la cavité sombre : aucune limite basse
          // dur, la rangée s'estompe au lieu de se terminer net.
          ctx.clip();
          const melt = ctx.createLinearGradient(0, top + maxDepth * 0.45, 0, top + maxDepth + 3);
          melt.addColorStop(0, "rgba(6, 3, 2, 0)");
          melt.addColorStop(1, "rgba(6, 3, 2, 0.85)");
          ctx.fillStyle = melt;
          ctx.fillRect(left, top, width, maxDepth + 6);
          // Séparations discrètes entre les dents, estompées vers la base.
          ctx.fillStyle = "rgba(58, 42, 28, 0.22)";
          for (let k = 1; k < 8; k++) {
            const x = left + (width * k) / 8;
            ctx.fillRect(x - 0.5, top, 1, maxDepth * 0.7);
          }
          // Ombre portée de la lèvre supérieure : détache les dents du visage.
          ctx.fillStyle = "rgba(8, 3, 2, 0.4)";
          ctx.beginPath();
          ctx.moveTo(tops[0][0], tops[0][1]);
          for (const [x, y] of tops) ctx.lineTo(x, y);
          for (let k = tops.length - 1; k >= 0; k--) ctx.lineTo(tops[k][0], tops[k][1] + 2.2);
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        }
      }
    }

    // 4. Les coins de la bouche restent dans l'ombre : les lèvres s'y
    // rejoignent, la cavité s'y fond sans découpe visible.
    for (const x of [left, right]) {
      const shadow = ctx.createRadialGradient(x, midY, 1, x, midY, width * 0.3);
      shadow.addColorStop(0, "rgba(2, 1, 1, 0.92)");
      shadow.addColorStop(1, "rgba(2, 1, 1, 0)");
      ctx.fillStyle = shadow;
      ctx.fillRect(left, top, width, height);
    }
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

    // Limites de l'ouverture réelle. L'intérieur reste dans son contour,
    // sans éventail de triangles qui amincit les dents et crée des stries.
    let left = Infinity, right = -Infinity, top = Infinity, bottom = -Infinity;
    for (let i = 0; i < COUNT; i++) {
      left = Math.min(left, this.destination[i * 2]);
      right = Math.max(right, this.destination[i * 2]);
      top = Math.min(top, this.destination[i * 2 + 1]);
      bottom = Math.max(bottom, this.destination[i * 2 + 1]);
    }

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

      // Fond opaque dans le contour : l'antialias des triangles ne doit pas
      // laisser réapparaître les lèvres fermées entre les facettes internes.
      // Cavité, langue et arc dentaire suivent la vraie courbe des lèvres.
      this.drawInterior(ctx, left, top, right, bottom);

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
      const lipBottomY = (top + bottom) / 2 + this.pose.open * 18;
      ctx.ellipse(CX, lipBottomY + 6, 32 + this.pose.wide * 8, 4 + this.pose.open * 3, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // 4. Masque feather pour bords doux
    ctx.globalCompositeOperation = "destination-in";
    ctx.drawImage(this.mask, 0, 0);
    ctx.globalCompositeOperation = "source-over";

    this.texture.needsUpdate = true;
  }

  reset() { this.lastKey = ""; this.motion.reset(); if (this.ready) this.render(REST_MOUTH); }

  destroy() {
    if (this.destroyed) return;
    this.destroyed = true;
    this.reset();
    if (this.overlay) {
      (this.parent || this.scene)?.remove?.(this.overlay);
      this.overlay.geometry?.dispose?.();
      this.overlay.material?.dispose?.();
    }
    this.texture?.dispose?.();
  }
}
