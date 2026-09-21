// ═══════════════════════════════════════════════════════════════
// KIRA — Slimy Orb with Flying GUI
// ═══════════════════════════════════════════════════════════════

let scene, camera, renderer;
let orb, orbGeometry, orbMaterial;
let stars, nebula, particles, energyRing;
let clock = new THREE.Clock();
let currentActivity = 'standby';

// ═══════════════════════════════════════════════════════════════
// Scene Setup
// ═══════════════════════════════════════════════════════════════

function initScene() {
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x000011);
  scene.fog = new THREE.FogExp2(0x000022, 0.0006);

  camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 2000);
  camera.position.set(0, 0, 10);
  camera.lookAt(0, 0, 0);

  const canvas = document.getElementById('scene');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.6;

  setupLighting();
  createStarfield();
  createNebula();
  createSlimyOrb();
  createParticles();
  createEnergyRing();

  window.addEventListener('resize', onWindowResize);
  animate();
}

// ═══════════════════════════════════════════════════════════════
// Lighting
// ═══════════════════════════════════════════════════════════════

function setupLighting() {
  scene.add(new THREE.AmbientLight(0x222244, 0.4));

  const key = new THREE.DirectionalLight(0x88aaff, 1.5);
  key.position.set(5, 5, 5);
  scene.add(key);

  const rim = new THREE.DirectionalLight(0x00ffff, 1);
  rim.position.set(-5, 2, -5);
  scene.add(rim);

  const bottom = new THREE.PointLight(0x00ff88, 0.8, 20);
  bottom.position.set(0, -5, 3);
  scene.add(bottom);

  const side = new THREE.PointLight(0xff00ff, 0.5, 15);
  side.position.set(-8, 0, 2);
  scene.add(side);

  const top = new THREE.PointLight(0x00ffff, 0.6, 15);
  top.position.set(0, 8, 0);
  scene.add(top);
}

// ═══════════════════════════════════════════════════════════════
// Starfield
// ═══════════════════════════════════════════════════════════════

function createStarfield() {
  const count = 6000;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const color = new THREE.Color();

  for (let i = 0; i < count; i++) {
    const radius = 150 + Math.random() * 850;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);

    pos[i * 3]     = radius * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    pos[i * 3 + 2] = radius * Math.cos(phi);

    const hue = Math.random() < 0.7 ? 0 : (Math.random() < 0.5 ? 0.6 : 0.15);
    const saturation = Math.random() * 0.3;
    const lightness = 0.7 + Math.random() * 0.3;
    color.setHSL(hue, saturation, lightness);

    colors[i * 3]     = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;
  }

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  stars = new THREE.Points(geo, new THREE.PointsMaterial({
    size: 1.8,
    vertexColors: true,
    transparent: true,
    opacity: 0.9,
    sizeAttenuation: true
  }));
  scene.add(stars);
}

// ═══════════════════════════════════════════════════════════════
// Nebula
// ═══════════════════════════════════════════════════════════════

function createNebula() {
  const count = 1000;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const color = new THREE.Color();

  for (let i = 0; i < count; i++) {
    const radius = 60 + Math.random() * 120;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);

    pos[i * 3]     = radius * Math.sin(phi) * Math.cos(theta) + (Math.random() - 0.5) * 40;
    pos[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta) * 0.4 + (Math.random() - 0.5) * 25;
    pos[i * 3 + 2] = radius * Math.cos(phi) - 120;

    const hue = 0.7 + Math.random() * 0.3;
    color.setHSL(hue, 0.9, 0.5);

    colors[i * 3]     = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;
  }

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  nebula = new THREE.Points(geo, new THREE.PointsMaterial({
    size: 10,
    vertexColors: true,
    transparent: true,
    opacity: 0.12,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true
  }));
  scene.add(nebula);
}

// ═══════════════════════════════════════════════════════════════
// Slimy Orb
// ═══════════════════════════════════════════════════════════════

function createSlimyOrb() {
  orbGeometry = new THREE.SphereGeometry(2.5, 64, 64);
  
  // Store original positions for morphing
  const positions = orbGeometry.attributes.position;
  const originalPositions = new Float32Array(positions.array.length);
  originalPositions.set(positions.array);
  orbGeometry.userData.originalPositions = originalPositions;

  orbMaterial = new THREE.MeshPhysicalMaterial({
    color: 0x00aaff,
    metalness: 0.3,
    roughness: 0.15,
    clearcoat: 1.0,
    clearcoatRoughness: 0.05,
    emissive: 0x004466,
    emissiveIntensity: 0.3,
    sheen: 1.0,
    sheenRoughness: 0.2,
    sheenColor: new THREE.Color(0x00ffff),
    transmission: 0.3,
    thickness: 1.5,
    ior: 1.5
  });

  orb = new THREE.Mesh(orbGeometry, orbMaterial);
  scene.add(orb);

  // Inner glow core
  const coreGeo = new THREE.SphereGeometry(1.8, 32, 32);
  const coreMat = new THREE.MeshBasicMaterial({
    color: 0x00ffff,
    transparent: true,
    opacity: 0.2,
    blending: THREE.AdditiveBlending
  });
  const core = new THREE.Mesh(coreGeo, coreMat);
  orb.add(core);
  orb.userData.core = core;

  // Outer glow
  const glowGeo = new THREE.SphereGeometry(3, 32, 32);
  const glowMat = new THREE.MeshBasicMaterial({
    color: 0x00ffff,
    transparent: true,
    opacity: 0.1,
    blending: THREE.AdditiveBlending,
    side: THREE.BackSide
  });
  const glow = new THREE.Mesh(glowGeo, glowMat);
  orb.add(glow);
  orb.userData.glow = glow;
}

// ═══════════════════════════════════════════════════════════════
// Particles (orbiting the orb)
// ═══════════════════════════════════════════════════════════════

function createParticles() {
  const count = 400;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const meta = [];
  const color = new THREE.Color();

  for (let i = 0; i < count; i++) {
    const radius = 3.5 + Math.random() * 2;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);

    pos[i * 3]     = radius * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    pos[i * 3 + 2] = radius * Math.cos(phi);

    const hue = 0.5 + Math.random() * 0.2;
    color.setHSL(hue, 0.9, 0.6);

    colors[i * 3]     = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;

    meta.push({
      radius,
      theta,
      phi,
      speed: 0.3 + Math.random() * 0.6,
      offset: Math.random() * Math.PI * 2
    });
  }

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  particles = new THREE.Points(geo, new THREE.PointsMaterial({
    size: 0.15,
    vertexColors: true,
    transparent: true,
    opacity: 0.8,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true
  }));
  particles.userData.meta = meta;
  scene.add(particles);
}

// ═══════════════════════════════════════════════════════════════
// Energy Ring
// ═══════════════════════════════════════════════════════════════

function createEnergyRing() {
  const ringGeo = new THREE.TorusGeometry(4, 0.08, 16, 100);
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0x00ffff,
    transparent: true,
    opacity: 0.4,
    blending: THREE.AdditiveBlending
  });

  energyRing = new THREE.Mesh(ringGeo, ringMat);
  energyRing.rotation.x = Math.PI / 2;
  scene.add(energyRing);

  // Second ring
  const ring2Geo = new THREE.TorusGeometry(4.5, 0.05, 16, 100);
  const ring2Mat = new THREE.MeshBasicMaterial({
    color: 0xff00ff,
    transparent: true,
    opacity: 0.3,
    blending: THREE.AdditiveBlending
  });

  const ring2 = new THREE.Mesh(ring2Geo, ring2Mat);
  ring2.rotation.x = Math.PI / 3;
  ring2.rotation.y = Math.PI / 4;
  scene.add(ring2);
  energyRing.userData.ring2 = ring2;
}

// ═══════════════════════════════════════════════════════════════
// Orb Morphing
// ═══════════════════════════════════════════════════════════════

function morphOrb(time, intensity) {
  if (!orbGeometry || !orbGeometry.userData.originalPositions) return;

  const positions = orbGeometry.attributes.position;
  const original = orbGeometry.userData.originalPositions;

  for (let i = 0; i < positions.count; i++) {
    const ox = original[i * 3];
    const oy = original[i * 3 + 1];
    const oz = original[i * 3 + 2];

    // Multi-layered noise for organic morphing
    const noise1 = Math.sin(ox * 2 + time * 1.5) * Math.cos(oy * 2 + time * 1.2) * Math.sin(oz * 2 + time * 1.8);
    const noise2 = Math.sin(ox * 4 + time * 2) * Math.cos(oy * 3 + time * 1.5) * 0.5;
    const noise3 = Math.sin(ox * 1.5 + time * 0.8) * Math.cos(oz * 1.5 + time * 1) * 0.3;

    const displacement = (noise1 + noise2 + noise3) * intensity * 0.15;

    // Calculate normal direction
    const len = Math.sqrt(ox * ox + oy * oy + oz * oz);
    const nx = ox / len;
    const ny = oy / len;
    const nz = oz / len;

    positions.setXYZ(
      i,
      ox + nx * displacement,
      oy + ny * displacement,
      oz + nz * displacement
    );
  }

  positions.needsUpdate = true;
  orbGeometry.computeVertexNormals();
}

// ═══════════════════════════════════════════════════════════════
// Animation Loop
// ═══════════════════════════════════════════════════════════════

function animate() {
  requestAnimationFrame(animate);

  const time = clock.getElapsedTime();

  // Orb constant movement and morphing
  if (orb) {
    // Floating motion
    orb.position.y = Math.sin(time * 0.6) * 0.4;
    orb.position.x = Math.sin(time * 0.3) * 0.2;
    
    // Rotation
    orb.rotation.y = time * 0.2;
    orb.rotation.x = Math.sin(time * 0.4) * 0.1;
    orb.rotation.z = Math.sin(time * 0.5) * 0.08;

    // Morphing intensity based on activity
    let morphIntensity = 1;
    if (currentActivity === 'thinking') morphIntensity = 2;
    if (currentActivity === 'speaking') morphIntensity = 2.5;
    if (currentActivity === 'active') morphIntensity = 1.5;

    morphOrb(time, morphIntensity);

    // Core pulsing
    if (orb.userData.core) {
      const pulse = 0.15 + Math.sin(time * 3) * 0.1;
      orb.userData.core.material.opacity = pulse;
      orb.userData.core.scale.setScalar(1 + Math.sin(time * 2) * 0.05);
    }

    // Outer glow pulsing
    if (orb.userData.glow) {
      orb.userData.glow.material.opacity = 0.08 + Math.sin(time * 2) * 0.04;
      orb.userData.glow.scale.setScalar(1 + Math.sin(time * 1.5) * 0.08);
    }
  }

  // Particles orbiting
  if (particles) {
    const pos = particles.geometry.attributes.position.array;
    const meta = particles.userData.meta;

    for (let i = 0; i < meta.length; i++) {
      const m = meta[i];
      const t = time * m.speed + m.offset;
      const theta = m.theta + t * 0.6;
      const phi = m.phi + Math.sin(t * 0.4) * 0.3;

      pos[i * 3]     = m.radius * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = m.radius * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = m.radius * Math.cos(phi);
    }

    particles.geometry.attributes.position.needsUpdate = true;
  }

  // Energy rings rotation
  if (energyRing) {
    energyRing.rotation.z = time * 0.3;
    energyRing.rotation.x = Math.PI / 2 + Math.sin(time * 0.5) * 0.2;

    if (energyRing.userData.ring2) {
      energyRing.userData.ring2.rotation.z = -time * 0.4;
      energyRing.userData.ring2.rotation.y = Math.PI / 4 + Math.sin(time * 0.6) * 0.3;
    }
  }

  // Stars slow rotation
  if (stars) {
    stars.rotation.y = time * 0.008;
    stars.rotation.x = Math.sin(time * 0.01) * 0.05;
  }

  // Nebula drift
  if (nebula) {
    nebula.rotation.y = time * 0.004;
    nebula.rotation.x = Math.sin(time * 0.008) * 0.08;
  }

  // Camera gentle movement
  camera.position.x = Math.sin(time * 0.1) * 1.5;
  camera.position.y = Math.sin(time * 0.15) * 0.8;
  camera.position.z = 10 + Math.sin(time * 0.12) * 0.5;
  camera.lookAt(0, 0, 0);

  renderer.render(scene, camera);
}

// ═══════════════════════════════════════════════════════════════
// Window Resize
// ═══════════════════════════════════════════════════════════════

function onWindowResize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}

// ═══════════════════════════════════════════════════════════════
// Activity State Changes
// ═══════════════════════════════════════════════════════════════

function setSceneActivity(state) {
  currentActivity = state;
  if (!orb) return;

  const orbColor = new THREE.Color();
  const emissiveColor = new THREE.Color();
  const glowColor = new THREE.Color();

  switch (state) {
    case 'thinking':
      orbColor.setHex(0xffaa00);
      emissiveColor.setHex(0x664400);
      glowColor.setHex(0xffaa00);
      break;

    case 'speaking':
      orbColor.setHex(0x00ff88);
      emissiveColor.setHex(0x006644);
      glowColor.setHex(0x00ff88);
      break;

    case 'active':
      orbColor.setHex(0x00ffff);
      emissiveColor.setHex(0x006666);
      glowColor.setHex(0x00ffff);
      break;

    default: // standby
      orbColor.setHex(0x00aaff);
      emissiveColor.setHex(0x004466);
      glowColor.setHex(0x00ffff);
  }

  orbMaterial.color.copy(orbColor);
  orbMaterial.emissive.copy(emissiveColor);

  if (orb.userData.core) {
    orb.userData.core.material.color.copy(glowColor);
  }
  if (orb.userData.glow) {
    orb.userData.glow.material.color.copy(glowColor);
  }
}

// Initialize
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initScene);
} else {
  initScene();
}
