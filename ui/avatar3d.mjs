// Avatar 3D de KIRA — d'après la référence validée : visage humain naturel,
// chignon noir plaqué, cou noir laqué à circuits dorés, buste mannequin posé
// sur un socle holographique à anneaux dorés. Géométrie pure Three.js.
// La mâchoire et les lèvres s'animent avec la voix (visèmes lips.mjs),
// synchronisées sur l'horloge audio réelle — aucun décalage.

const GOLD = 0xC2A66B;
const GOLD_BRIGHT = 0xE3D3A6;
const SKIN = 0xD8A583;
const HAIR = 0x151009;
const BUST = 0x0D0A07;
const BROW = 0x3A2A1C;
const LIP = 0xB4705F;
const IRIS = 0x5A4632;

function materials(THREE) {
  return {
    skin: new THREE.MeshStandardMaterial({ color: SKIN, roughness: 0.52, metalness: 0.04 }),
    hair: new THREE.MeshStandardMaterial({ color: HAIR, roughness: 0.28, metalness: 0.3 }),
    bust: new THREE.MeshStandardMaterial({ color: BUST, roughness: 0.16, metalness: 0.62 }),
    circuit: new THREE.MeshBasicMaterial({ color: GOLD }),
    circuitBright: new THREE.MeshBasicMaterial({ color: GOLD_BRIGHT }),
    brow: new THREE.MeshStandardMaterial({ color: BROW, roughness: 0.6 }),
    lip: new THREE.MeshStandardMaterial({ color: LIP, roughness: 0.42, metalness: 0.05 }),
    mouthIn: new THREE.MeshBasicMaterial({ color: 0x401016, transparent: true, opacity: 0 }),
    eyeWhite: new THREE.MeshStandardMaterial({ color: 0xF3EDE4, roughness: 0.3, metalness: 0.02 }),
    iris: new THREE.MeshStandardMaterial({ color: IRIS, roughness: 0.25, metalness: 0.05 }),
    glow: new THREE.MeshBasicMaterial({ color: GOLD, transparent: true, opacity: 0.85 }),
    glowSoft: new THREE.MeshBasicMaterial({ color: GOLD, transparent: true, opacity: 0.38 }),
  };
}

export function createAvatar3D(THREE, scene) {
  const M = materials(THREE);
  const group = new THREE.Group();
  group.position.set(0, 0.35, 2.4);
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

  // Visage (peau naturelle)
  add(head, new THREE.SphereGeometry(1, 48, 48), M.skin, [0, 0, 0.02], [0.8, 1.0, 0.86]);
  // Pommettes / volume des joues
  add(head, new THREE.SphereGeometry(0.3, 24, 24), M.skin, [-0.36, -0.18, 0.62], [0.9, 0.62, 0.5]);
  add(head, new THREE.SphereGeometry(0.3, 24, 24), M.skin, [0.36, -0.18, 0.62], [0.9, 0.62, 0.5]);
  // Menton doux
  add(head, new THREE.SphereGeometry(0.22, 24, 24), M.skin, [0, -0.62, 0.56], [0.85, 0.7, 0.7]);

  // Cheveux : calotte noire satinée plaquée + chignon bas
  add(head, new THREE.SphereGeometry(1.03, 48, 48, 0, Math.PI * 2, 0, Math.PI * 0.58), M.hair, [0, 0.05, -0.03], [0.9, 1.05, 0.98]);
  add(head, new THREE.SphereGeometry(0.55, 32, 32), M.hair, [0, -0.05, -0.55], [0.88, 1.0, 0.85]);
  add(head, new THREE.SphereGeometry(0.32, 24, 24), M.hair, [0, -0.42, -0.82], [1.0, 0.8, 0.9]);

  // Sourcils naturels
  add(head, new THREE.TorusGeometry(0.13, 0.017, 8, 24, Math.PI * 0.5), M.brow, [-0.3, 0.24, 0.8], null, [0, 0, Math.PI * 0.72]);
  add(head, new THREE.TorusGeometry(0.13, 0.017, 8, 24, Math.PI * 0.5), M.brow, [0.3, 0.24, 0.8], null, [0, 0, Math.PI * 0.72]);

  // Nez discret
  add(head, new THREE.SphereGeometry(0.11, 24, 24), M.skin, [0, -0.16, 0.86], [0.55, 1.05, 0.8]);

  // ── YEUX ──────────────────────────────────────────
  const eyes = new THREE.Group();
  head.add(eyes);
  for (const side of [-1, 1]) {
    const eye = new THREE.Group();
    eye.position.set(side * 0.28, 0.08, 0.72);
    add(eye, new THREE.SphereGeometry(0.088, 24, 24), M.eyeWhite, null, [1, 0.72, 0.5]);
    add(eye, new THREE.SphereGeometry(0.044, 20, 20), M.iris, [0, 0, 0.05]);
    add(eye, new THREE.SphereGeometry(0.013, 10, 10), M.circuitBright, [0.016, 0.02, 0.086]);
    eyes.add(eye);
  }

  // ── BOUCHE (mâchoire animée) ──────────────────────
  const jaw = new THREE.Group();
  head.add(jaw);
  add(jaw, new THREE.SphereGeometry(0.42, 32, 32), M.skin, [0, -0.6, 0.42], [0.6, 0.5, 0.55]);

  const lips = new THREE.Group();
  head.add(lips);
  const upperLipBaseY = -0.385;
  const lowerLipBaseY = -0.45;
  // Arcs en « U » dans le plan du visage (torus XY, arc centré en bas).
  const upperLip = add(lips, new THREE.TorusGeometry(0.16, 0.036, 12, 32, Math.PI * 0.9), M.lip, [0, upperLipBaseY, 0.8], null, [0, 0, Math.PI * 1.05]);
  const lowerLip = add(lips, new THREE.TorusGeometry(0.17, 0.042, 12, 32, Math.PI * 0.8), M.lip, [0, lowerLipBaseY, 0.8], null, [0, 0, Math.PI * 1.1]);
  const mouthInner = add(lips, new THREE.CircleGeometry(0.15, 24), M.mouthIn, [0, -0.42, 0.76], [1, 0.25, 1]);

  // ── COU : noir laqué + circuits dorés ─────────────
  add(group, new THREE.CylinderGeometry(0.23, 0.26, 0.55, 24), M.bust, [0, -1.12, 0.02]);
  add(group, new THREE.TorusGeometry(0.24, 0.006, 8, 32), M.circuit, [0, -0.95, 0.02], [Math.PI / 2, 0, 0]);
  add(group, new THREE.TorusGeometry(0.25, 0.006, 8, 32), M.circuit, [0, -1.18, 0.02], [Math.PI / 2, 0, 0]);
  // Lignes verticales de circuit devant le cou
  add(group, new THREE.BoxGeometry(0.012, 0.5, 0.012), M.circuit, [-0.07, -1.12, 0.235]);
  add(group, new THREE.BoxGeometry(0.012, 0.5, 0.012), M.circuit, [0.07, -1.12, 0.235]);
  add(group, new THREE.BoxGeometry(0.01, 0.42, 0.01), M.circuitBright, [0, -1.08, 0.24]);

  // ── BUSTE mannequin (profil élégant, noir laqué) ──
  const bustPoints = [
    new THREE.Vector2(0.26, -1.34),
    new THREE.Vector2(0.32, -1.44),
    new THREE.Vector2(0.5, -1.6),
    new THREE.Vector2(0.76, -1.82),
    new THREE.Vector2(0.93, -1.98),
    new THREE.Vector2(0.99, -2.12),
    new THREE.Vector2(0.9, -2.22),
  ];
  const bust = new THREE.Mesh(new THREE.LatheGeometry(bustPoints, 48), M.bust);
  group.add(bust);
  // Circuits dorés du décolleté
  add(group, new THREE.TorusGeometry(0.4, 0.007, 8, 48), M.circuit, [0, -1.5, 0.06], [Math.PI / 2.15, 0, 0]);
  add(group, new THREE.TorusGeometry(0.62, 0.006, 8, 48), M.glowSoft, [0, -1.74, 0.05], [Math.PI / 2.3, 0, 0]);
  add(group, new THREE.BoxGeometry(0.012, 0.3, 0.012), M.circuit, [0, -1.7, 0.42]);

  // ── SOCLE holographique (anneaux dorés au sol) ────
  const baseY = -2.24;
  add(group, new THREE.CylinderGeometry(1.05, 1.18, 0.07, 48), M.bust, [0, baseY, 0]);
  add(group, new THREE.TorusGeometry(1.11, 0.014, 8, 64), M.circuit, [0, baseY + 0.04, 0], [Math.PI / 2, 0, 0]);
  const ring1 = add(group, new THREE.TorusGeometry(1.45, 0.012, 8, 72), M.glow, [0, baseY + 0.02, 0], null, [Math.PI / 2, 0, 0]);
  const ring2 = add(group, new THREE.TorusGeometry(1.78, 0.009, 8, 80), M.glowSoft, [0, baseY + 0.02, 0], null, [Math.PI / 2, 0, 0]);
  const ring3 = add(group, new THREE.TorusGeometry(2.1, 0.007, 8, 88), M.glowSoft, [0, baseY + 0.02, 0], null, [Math.PI / 2, 0, 0]);

  // Lueurs : visage + socle
  const faceLight = new THREE.PointLight(0xFFE3C0, 2.4, 7);
  faceLight.position.set(0, 0.3, 2.8);
  group.add(faceLight);
  const baseGlow = new THREE.PointLight(GOLD, 1.6, 5);
  baseGlow.position.set(0, baseY + 0.3, 0.8);
  group.add(baseGlow);

  // ── ANIMATION ─────────────────────────────────────
  const state = { openness: 0, wide: 0, round: 0, lastBlink: 0, blinkPhase: -1 };
  const lerp = (a, b, t) => a + (b - a) * t;

  function update({ mouth, level = 0, energy = 0, time = 0, active = false, dt = 1 / 60 }) {
    const pose = mouth || { open: 0, wide: 0, round: 0 };
    const gate = active ? Math.min(1, level * 3.2) : 0;
    const targetOpen = Math.min(1, pose.open || 0) * (0.25 + 0.75 * gate);
    const targetWide = Math.min(1, pose.wide || 0) * gate;
    const targetRound = Math.min(1, pose.round || 0) * gate;

    state.openness = lerp(state.openness, targetOpen, 1 - Math.exp(-dt / 0.03));
    state.wide = lerp(state.wide, targetWide, 1 - Math.exp(-dt / 0.04));
    state.round = lerp(state.round, targetRound, 1 - Math.exp(-dt / 0.04));

    jaw.rotation.x = state.openness * 0.28;
    jaw.position.y = -state.openness * 0.05;
    lowerLip.position.y = lowerLipBaseY - state.openness * 0.085;
    mouthInner.scale.set(1 + state.openness * 0.25, 0.25 + state.openness * 1.35, 1);
    mouthInner.material.opacity = Math.min(1, state.openness * 3);
    lips.scale.set(1 + state.wide * 0.17 - state.round * 0.2, 1 - state.round * 0.12, 1);
    lips.position.z = state.round * 0.04;

    // Clignement toutes les 3 à 5 s (130 ms)
    const cycle = time - state.lastBlink;
    if (state.blinkPhase < 0 && cycle > 3.2 + Math.abs(Math.sin(time * 0.7)) * 1.8) {
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

    // Vie : micro-mouvements de tête + respiration + anneaux qui tournent
    head.rotation.y = Math.sin(time * 0.35) * 0.055 + energy * Math.sin(time * 2.3) * 0.025;
    head.rotation.x = Math.sin(time * 0.27) * 0.028 + state.openness * 0.03;
    ring1.rotation.z = time * 0.25;
    ring2.rotation.z = -time * 0.16;
    ring3.rotation.z = time * 0.09;
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
