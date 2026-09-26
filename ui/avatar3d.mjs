// Avatar 3D de KIRA — androïde féminine construite en géométrie pure
// (aucune photo). La mâchoire et les lèvres s'animent avec la voix via les
// visèmes de lips.mjs/speech.mjs, synchronisées sur l'horloge audio réelle.
const GOLD = 0xC2A66B;
const GOLD_BRIGHT = 0xE3D3A6;
const GUNMETAL = 0x18120a;
const IVORY = 0xE9CDA9;
const DARK = 0x0d0a06;

function materials(THREE) {
  return {
    gold: new THREE.MeshStandardMaterial({ color: GOLD, metalness: 0.92, roughness: 0.32 }),
    goldBright: new THREE.MeshStandardMaterial({ color: GOLD_BRIGHT, metalness: 0.9, roughness: 0.25, emissive: GOLD, emissiveIntensity: 0.25 }),
    seam: new THREE.MeshBasicMaterial({ color: GOLD_BRIGHT }),
    gunmetal: new THREE.MeshStandardMaterial({ color: GUNMETAL, metalness: 0.85, roughness: 0.45 }),
    dark: new THREE.MeshStandardMaterial({ color: DARK, metalness: 0.55, roughness: 0.55 }),
    ivory: new THREE.MeshStandardMaterial({ color: IVORY, metalness: 0.12, roughness: 0.62 }),
    lip: new THREE.MeshStandardMaterial({ color: 0xB4705F, metalness: 0.08, roughness: 0.5 }),
    mouthIn: new THREE.MeshBasicMaterial({ color: 0x401016, transparent: true, opacity: 0 }),
    eyeWhite: new THREE.MeshStandardMaterial({ color: 0xF3EDE4, metalness: 0.05, roughness: 0.35 }),
    iris: new THREE.MeshStandardMaterial({ color: 0x4A3220, metalness: 0.1, roughness: 0.3 }),
  };
}

export function createAvatar3D(THREE, scene) {
  const M = materials(THREE);
  const group = new THREE.Group();
  group.position.set(0, 0.4, 2.4);
  group.scale.setScalar(1.12);
  scene.add(group);

  const add = (parent, geo, mat, pos, scale, rot) => {
    const mesh = new THREE.Mesh(geo, mat);
    if (pos) mesh.position.set(pos[0], pos[1], pos[2]);
    if (scale) mesh.scale.set(scale[0], scale[1], scale[2]);
    if (rot) mesh.rotation.set(rot[0], rot[1], rot[2]);
    parent.add(mesh);
    return mesh;
  };

  // ── TÊTE ──────────────────────────────────────────
  const head = new THREE.Group();
  group.add(head);

  // Crâne (structure)
  add(head, new THREE.SphereGeometry(1, 48, 48), M.gunmetal, [0, 0, 0], [0.88, 1.06, 0.95]);
  // Casque / cheveux ajustés noir satin
  add(head, new THREE.SphereGeometry(1.02, 48, 48, 0, Math.PI * 2, 0, Math.PI * 0.62), M.dark, [0, 0.04, -0.02], [0.92, 1.06, 0.99]);
  // Panneau arrière
  add(head, new THREE.SphereGeometry(0.95, 32, 32), M.dark, [0, -0.05, -0.22], [0.86, 1.02, 0.78]);
  // Coutures lumineuses du casque
  add(head, new THREE.TorusGeometry(0.9, 0.008, 8, 64), M.seam, [0, 0.42, 0.05], [Math.PI / 2.25, 0, 0]);
  add(head, new THREE.TorusGeometry(0.72, 0.006, 8, 64), M.seam, [0, 0.62, -0.12], [Math.PI / 2.6, 0, 0]);
  // Bandeau frontal doré
  add(head, new THREE.TorusGeometry(0.84, 0.02, 10, 64, Math.PI * 0.9), M.goldBright, [0, 0.34, 0.28], [Math.PI / 2.1, 0, 0]);

  // Visage ivoire (ovale devant la structure)
  add(head, new THREE.SphereGeometry(0.87, 48, 48), M.ivory, [0, -0.02, 0.09], [0.82, 0.99, 0.86]);

  // Pods latéraux (oreilles androïde)
  for (const side of [-1, 1]) {
    add(head, new THREE.CylinderGeometry(0.13, 0.13, 0.1, 24), M.gold, [side * 0.87, -0.02, 0.02], null, [0, 0, Math.PI / 2]);
    add(head, new THREE.TorusGeometry(0.13, 0.012, 8, 32), M.seam, [side * 0.93, -0.02, 0.02], null, [0, Math.PI / 2, 0]);
  }

  // Sourcils
  add(head, new THREE.TorusGeometry(0.13, 0.016, 8, 24, Math.PI * 0.55), M.goldBright, [-0.3, 0.26, 0.79], null, [0, 0, Math.PI * 0.72]);
  add(head, new THREE.TorusGeometry(0.13, 0.016, 8, 24, Math.PI * 0.55), M.goldBright, [0.3, 0.26, 0.79], null, [0, 0, Math.PI * 0.72]);

  // Nez discret
  add(head, new THREE.SphereGeometry(0.12, 24, 24), M.ivory, [0, -0.16, 0.9], [0.5, 1.0, 0.75]);

  // ── YEUX ──────────────────────────────────────────
  const eyes = new THREE.Group();
  head.add(eyes);
  for (const side of [-1, 1]) {
    const eye = new THREE.Group();
    eye.position.set(side * 0.29, 0.1, 0.76);
    add(eye, new THREE.SphereGeometry(0.085, 24, 24), M.eyeWhite, null, [1, 0.72, 0.55]);
    add(eye, new THREE.SphereGeometry(0.042, 20, 20), M.iris, [0, 0, 0.05]);
    add(eye, new THREE.SphereGeometry(0.012, 10, 10), M.seam, [0.015, 0.02, 0.085]);
    eyes.add(eye);
  }

  // ── BOUCHE ────────────────────────────────────────
  // Groupe mâchoire : menton + lèvre inférieure + intérieur bougent ensemble.
  const jaw = new THREE.Group();
  head.add(jaw);
  const jawBaseY = -0.62;
  add(jaw, new THREE.SphereGeometry(0.5, 32, 32), M.ivory, [0, jawBaseY, 0.5], [0.52, 0.44, 0.44]);

  const lips = new THREE.Group();
  head.add(lips);
  const upperLipBaseY = -0.30;
  const lowerLipBaseY = -0.365;
  // Arcs en « U » dans le plan du visage (torus XY, arc centré en bas).
  const upperLip = add(lips, new THREE.TorusGeometry(0.16, 0.036, 12, 32, Math.PI * 0.9), M.lip, [0, upperLipBaseY, 0.84], null, [0, 0, Math.PI * 1.05]);
  const lowerLip = add(lips, new THREE.TorusGeometry(0.17, 0.042, 12, 32, Math.PI * 0.8), M.lip, [0, lowerLipBaseY, 0.84], null, [0, 0, Math.PI * 1.1]);
  const mouthInner = add(lips, new THREE.CircleGeometry(0.15, 24), M.mouthIn, [0, -0.335, 0.8], [1, 0.25, 1]);

  // ── COU ───────────────────────────────────────────
  add(group, new THREE.CylinderGeometry(0.26, 0.3, 0.16, 24), M.gold, [0, -1.02, 0.05]);
  add(group, new THREE.TorusGeometry(0.28, 0.012, 8, 32), M.seam, [0, -0.94, 0.05], [Math.PI / 2, 0, 0]);
  add(group, new THREE.CylinderGeometry(0.3, 0.34, 0.16, 24), M.gunmetal, [0, -1.2, 0.05]);
  add(group, new THREE.TorusGeometry(0.32, 0.012, 8, 32), M.seam, [0, -1.12, 0.05], [Math.PI / 2, 0, 0]);
  add(group, new THREE.CylinderGeometry(0.34, 0.38, 0.14, 24), M.gold, [0, -1.37, 0.05]);

  // ── ÉPAULES / BUSTE ───────────────────────────────
  add(group, new THREE.TorusGeometry(0.52, 0.1, 12, 48), M.gunmetal, [0, -1.52, 0.02], [Math.PI / 2, 0, 0]);
  add(group, new THREE.TorusGeometry(0.52, 0.02, 8, 48), M.gold, [0, -1.46, 0.02], [Math.PI / 2, 0, 0]);
  for (const side of [-1, 1]) {
    add(group, new THREE.SphereGeometry(0.3, 24, 24), M.gold, [side * 0.72, -1.6, 0]);
  }
  add(group, new THREE.SphereGeometry(0.62, 32, 32), M.dark, [0, -1.85, 0], [1.15, 0.7, 0.75]);

  // Lueur douce pour lire le visage
  const faceLight = new THREE.PointLight(0xFFE7C2, 2.2, 7);
  faceLight.position.set(0, 0.3, 2.6);
  group.add(faceLight);

  // ── ANIMATION ─────────────────────────────────────
  const state = {
    openness: 0, wide: 0, round: 0,
    lastBlink: 0, blinkPhase: -1,
  };
  const lerp = (a, b, t) => a + (b - a) * t;

  function update({ mouth, level = 0, energy = 0, time = 0, active = false, dt = 1 / 60 }) {
    const pose = mouth || { open: 0, wide: 0, round: 0 };
    // La voix module l'ouverture : silencieuse = lèvres closes.
    const gate = active ? Math.min(1, level * 3.2) : 0;
    const targetOpen = Math.min(1, pose.open || 0) * (0.25 + 0.75 * gate);
    const targetWide = Math.min(1, pose.wide || 0) * gate;
    const targetRound = Math.min(1, pose.round || 0) * gate;

    state.openness = lerp(state.openness, targetOpen, 1 - Math.exp(-dt / 0.03));
    state.wide = lerp(state.wide, targetWide, 1 - Math.exp(-dt / 0.04));
    state.round = lerp(state.round, targetRound, 1 - Math.exp(-dt / 0.04));

    // Mâchoire + lèvre inférieure descendent ; l'intérieur s'ouvre.
    jaw.rotation.x = state.openness * 0.3;
    jaw.position.y = -state.openness * 0.05;
    lowerLip.position.y = lowerLipBaseY - state.openness * 0.085;
    mouthInner.scale.set(1 + state.openness * 0.25, 0.25 + state.openness * 1.35, 1);
    mouthInner.material.opacity = Math.min(1, state.openness * 3);

    // Étire / arrondit les lèvres (EE vs OH)
    lips.scale.set(1 + state.wide * 0.17 - state.round * 0.2, 1 - state.round * 0.12, 1);
    lips.position.z = state.round * 0.04;

    // Clignement : toutes les 3 à 5 s, 130 ms
    const cycle = time - state.lastBlink;
    if (state.blinkPhase < 0 && cycle > 3.2 + (Math.abs(Math.sin(time * 0.7)) * 1.8)) {
      state.blinkPhase = 0;
      state.lastBlink = time;
    }
    let eyeScale = 1;
    if (state.blinkPhase >= 0) {
      state.blinkPhase += dt;
      const p = state.blinkPhase / 0.13;
      eyeScale = p >= 1 ? 1 : Math.abs(1 - 2 * p) * 0.92 + 0.08;
      if (p >= 1) state.blinkPhase = -1;
    }
    eyes.scale.set(1, eyeScale, 1);

    // Vie : légère rotation de tête + respiration
    head.rotation.y = Math.sin(time * 0.35) * 0.055 + energy * Math.sin(time * 2.3) * 0.025;
    head.rotation.x = Math.sin(time * 0.27) * 0.028 + state.openness * 0.03;
    const breathe = 1 + energy * 0.02;
    group.scale.set(1.12 * breathe, 1.12 * (1 + energy * 0.025), 1.12 * breathe);
  }

  function destroy() {
    scene.remove(group);
    group.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material && obj.material.dispose) obj.material.dispose();
    });
  }

  return { group, update, destroy };
}
