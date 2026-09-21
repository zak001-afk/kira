// ═══════════════════════════════════════════════════════════════
// KIRA — Slimy Robot in Space
// ═══════════════════════════════════════════════════════════════

let scene, camera, renderer;
let robot, robotGroup;
let stars, nebula, slimeParticles, energyField;
let clock = new THREE.Clock();
let currentActivity = 'standby';

// ═══════════════════════════════════════════════════════════════
// Scene Setup
// ═══════════════════════════════════════════════════════════════

function initScene() {
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x000011);
  scene.fog = new THREE.FogExp2(0x000022, 0.0008);

  camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 2000);
  camera.position.set(0, 2, 12);
  camera.lookAt(0, 0, 0);

  const canvas = document.getElementById('scene');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.5;

  setupLighting();
  createStarfield();
  createNebula();
  createRobot();
  createSlimeParticles();
  createEnergyField();

  window.addEventListener('resize', onWindowResize);
  animate();
}

// ═══════════════════════════════════════════════════════════════
// Lighting
// ═══════════════════════════════════════════════════════════════

function setupLighting() {
  // Ambient space light
  scene.add(new THREE.AmbientLight(0x222244, 0.3));

  // Key light (blue-white)
  const key = new THREE.DirectionalLight(0x88aaff, 1.2);
  key.position.set(5, 5, 5);
  scene.add(key);

  // Rim light (cyan for edge highlight)
  const rim = new THREE.DirectionalLight(0x00ffff, 0.8);
  rim.position.set(-5, 2, -5);
  scene.add(rim);

  // Bottom accent (green for slime glow)
  const bottom = new THREE.PointLight(0x00ff88, 0.6, 20);
  bottom.position.set(0, -5, 3);
  scene.add(bottom);

  // Side accent (purple)
  const side = new THREE.PointLight(0xff00ff, 0.4, 15);
  side.position.set(-8, 0, 2);
  scene.add(side);
}

// ═══════════════════════════════════════════════════════════════
// Starfield
// ═══════════════════════════════════════════════════════════════

function createStarfield() {
  const count = 5000;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const sizes = new Float32Array(count);

  const color = new THREE.Color();

  for (let i = 0; i < count; i++) {
    // Random position in a large sphere
    const radius = 200 + Math.random() * 800;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);

    pos[i * 3]     = radius * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    pos[i * 3 + 2] = radius * Math.cos(phi);

    // Star colors (white, blue-white, yellow-white)
    const hue = Math.random() < 0.7 ? 0 : (Math.random() < 0.5 ? 0.6 : 0.15);
    const saturation = Math.random() * 0.3;
    const lightness = 0.7 + Math.random() * 0.3;
    color.setHSL(hue, saturation, lightness);

    colors[i * 3]     = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;

    sizes[i] = 0.5 + Math.random() * 2;
  }

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  stars = new THREE.Points(geo, new THREE.PointsMaterial({
    size: 1.5,
    vertexColors: true,
    transparent: true,
    opacity: 0.8,
    sizeAttenuation: true
  }));
  scene.add(stars);
}

// ═══════════════════════════════════════════════════════════════
// Nebula (colorful space cloud)
// ═══════════════════════════════════════════════════════════════

function createNebula() {
  const count = 800;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);

  const color = new THREE.Color();

  for (let i = 0; i < count; i++) {
    // Cluster nebula particles
    const radius = 50 + Math.random() * 100;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);

    pos[i * 3]     = radius * Math.sin(phi) * Math.cos(theta) + (Math.random() - 0.5) * 30;
    pos[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta) * 0.3 + (Math.random() - 0.5) * 20;
    pos[i * 3 + 2] = radius * Math.cos(phi) - 100;

    // Nebula colors (purple, blue, cyan, pink)
    const hue = 0.7 + Math.random() * 0.3;
    color.setHSL(hue, 0.8, 0.5);

    colors[i * 3]     = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;
  }

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  nebula = new THREE.Points(geo, new THREE.PointsMaterial({
    size: 8,
    vertexColors: true,
    transparent: true,
    opacity: 0.15,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true
  }));
  scene.add(nebula);
}

// ═══════════════════════════════════════════════════════════════
// Slimy Robot
// ═══════════════════════════════════════════════════════════════

function createRobot() {
  robotGroup = new THREE.Group();

  // Main body (oval/sphere shape)
  const bodyGeo = new THREE.SphereGeometry(2, 32, 32);
  bodyGeo.scale(1, 1.3, 0.9); // Make it oval

  const bodyMat = new THREE.MeshPhysicalMaterial({
    color: 0x224466,
    metalness: 0.7,
    roughness: 0.2,
    clearcoat: 1.0,
    clearcoatRoughness: 0.1,
    emissive: 0x001133,
    emissiveIntensity: 0.2,
    sheen: 1.0,
    sheenRoughness: 0.3,
    sheenColor: new THREE.Color(0x00ffaa)
  });

  const body = new THREE.Mesh(bodyGeo, bodyMat);
  robotGroup.add(body);

  // Head (smaller sphere on top)
  const headGeo = new THREE.SphereGeometry(1.2, 32, 32);
  const head = new THREE.Mesh(headGeo, bodyMat.clone());
  head.position.y = 2.5;
  robotGroup.add(head);

  // Eyes (glowing cyan spheres)
  const eyeGeo = new THREE.SphereGeometry(0.3, 16, 16);
  const eyeMat = new THREE.MeshBasicMaterial({
    color: 0x00ffff,
    emissive: 0x00ffff,
    emissiveIntensity: 1
  });

  const leftEye = new THREE.Mesh(eyeGeo, eyeMat);
  leftEye.position.set(-0.4, 2.7, 1);
  robotGroup.add(leftEye);

  const rightEye = new THREE.Mesh(eyeGeo, eyeMat);
  rightEye.position.set(0.4, 2.7, 1);
  robotGroup.add(rightEye);

  // Eye glow
  const eyeGlowGeo = new THREE.SphereGeometry(0.4, 16, 16);
  const eyeGlowMat = new THREE.MeshBasicMaterial({
    color: 0x00ffff,
    transparent: true,
    opacity: 0.3,
    blending: THREE.AdditiveBlending
  });

  const leftGlow = new THREE.Mesh(eyeGlowGeo, eyeGlowMat);
  leftGlow.position.copy(leftEye.position);
  robotGroup.add(leftGlow);

  const rightGlow = new THREE.Mesh(eyeGlowGeo, eyeGlowMat);
  rightGlow.position.copy(rightEye.position);
  robotGroup.add(rightGlow);

  // Antenna
  const antennaGeo = new THREE.CylinderGeometry(0.05, 0.08, 1.5, 8);
  const antennaMat = new THREE.MeshPhysicalMaterial({
    color: 0x444444,
    metalness: 0.9,
    roughness: 0.3
  });
  const antenna = new THREE.Mesh(antennaGeo, antennaMat);
  antenna.position.y = 3.8;
  robotGroup.add(antenna);

  // Antenna tip (glowing)
  const tipGeo = new THREE.SphereGeometry(0.15, 16, 16);
  const tipMat = new THREE.MeshBasicMaterial({
    color: 0xff0088,
    emissive: 0xff0088,
    emissiveIntensity: 1
  });
  const tip = new THREE.Mesh(tipGeo, tipMat);
  tip.position.y = 4.6;
  robotGroup.add(tip);

  // Arms (cylinders)
  const armGeo = new THREE.CylinderGeometry(0.15, 0.2, 2, 8);
  const armMat = bodyMat.clone();

  const leftArm = new THREE.Mesh(armGeo, armMat);
  leftArm.position.set(-2.2, 0, 0);
  leftArm.rotation.z = Math.PI / 6;
  robotGroup.add(leftArm);

  const rightArm = new THREE.Mesh(armGeo, armMat);
  rightArm.position.set(2.2, 0, 0);
  rightArm.rotation.z = -Math.PI / 6;
  robotGroup.add(rightArm);

  // Hands (spheres)
  const handGeo = new THREE.SphereGeometry(0.3, 16, 16);
  const leftHand = new THREE.Mesh(handGeo, armMat);
  leftHand.position.set(-2.8, -0.9, 0);
  robotGroup.add(leftHand);

  const rightHand = new THREE.Mesh(handGeo, armMat);
  rightHand.position.set(2.8, -0.9, 0);
  robotGroup.add(rightHand);

  // Panel details on body
  const panelGeo = new THREE.BoxGeometry(0.8, 0.4, 0.1);
  const panelMat = new THREE.MeshPhysicalMaterial({
    color: 0x111111,
    metalness: 0.8,
    roughness: 0.4,
    emissive: 0x00ff88,
    emissiveIntensity: 0.3
  });

  const panel1 = new THREE.Mesh(panelGeo, panelMat);
  panel1.position.set(0, 0.5, 1.8);
  robotGroup.add(panel1);

  const panel2 = new THREE.Mesh(panelGeo, panelMat);
  panel2.position.set(0, -0.5, 1.8);
  robotGroup.add(panel2);

  // Store references
  robot = {
    group: robotGroup,
    body,
    head,
    leftEye,
    rightEye,
    leftGlow,
    rightGlow,
    antenna,
    tip,
    leftArm,
    rightArm,
    leftHand,
    rightHand,
    panel1,
    panel2
  };

  scene.add(robotGroup);
}

// ═══════════════════════════════════════════════════════════════
// Slime Particles (dripping effect)
// ═══════════════════════════════════════════════════════════════

function createSlimeParticles() {
  const count = 300;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const vel = new Float32Array(count * 3);

  for (let i = 0; i < count; i++) {
    // Start near robot surface
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const r = 2 + Math.random() * 0.5;

    pos[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 1.3;
    pos[i * 3 + 2] = r * Math.cos(phi) * 0.9;

    vel[i * 3]     = (Math.random() - 0.5) * 0.02;
    vel[i * 3 + 1] = -0.02 - Math.random() * 0.03;
    vel[i * 3 + 2] = (Math.random() - 0.5) * 0.02;
  }

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));

  slimeParticles = new THREE.Points(geo, new THREE.PointsMaterial({
    color: 0x00ff88,
    size: 0.15,
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true
  }));
  slimeParticles.userData.velocities = vel;
  scene.add(slimeParticles);
}

// ═══════════════════════════════════════════════════════════════
// Energy Field (orbiting particles)
// ═══════════════════════════════════════════════════════════════

function createEnergyField() {
  const count = 500;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const meta = [];

  const color = new THREE.Color();

  for (let i = 0; i < count; i++) {
    const radius = 3 + Math.random() * 2;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);

    pos[i * 3]     = radius * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    pos[i * 3 + 2] = radius * Math.cos(phi);

    // Cyan to purple gradient
    const hue = 0.5 + Math.random() * 0.3;
    color.setHSL(hue, 0.9, 0.6);

    colors[i * 3]     = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;

    meta.push({
      radius,
      theta,
      phi,
      speed: 0.2 + Math.random() * 0.5,
      offset: Math.random() * Math.PI * 2
    });
  }

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  energyField = new THREE.Points(geo, new THREE.PointsMaterial({
    size: 0.12,
    vertexColors: true,
    transparent: true,
    opacity: 0.7,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true
  }));
  energyField.userData.meta = meta;
  scene.add(energyField);
}

// ═══════════════════════════════════════════════════════════════
// Animation Loop
// ═══════════════════════════════════════════════════════════════

function animate() {
  requestAnimationFrame(animate);

  const time = clock.getElapsedTime();

  // Robot floating motion
  if (robotGroup) {
    robotGroup.position.y = Math.sin(time * 0.5) * 0.5;
    robotGroup.rotation.y = Math.sin(time * 0.3) * 0.2;
    robotGroup.rotation.x = Math.sin(time * 0.2) * 0.05;
    robotGroup.rotation.z = Math.sin(time * 0.4) * 0.08;
  }

  // Eye pulsing
  if (robot) {
    const pulse = 0.8 + Math.sin(time * 3) * 0.2;
    robot.leftEye.material.emissiveIntensity = pulse;
    robot.rightEye.material.emissiveIntensity = pulse;
    robot.leftGlow.material.opacity = 0.2 + Math.sin(time * 3) * 0.1;
    robot.rightGlow.material.opacity = 0.2 + Math.sin(time * 3) * 0.1;

    // Antenna tip blinking
    robot.tip.material.emissiveIntensity = (Math.sin(time * 5) > 0.5) ? 1 : 0.2;

    // Arm movement
    robot.leftArm.rotation.x = Math.sin(time * 0.8) * 0.3;
    robot.rightArm.rotation.x = Math.sin(time * 0.8 + Math.PI) * 0.3;

    // Panel glow
    robot.panel1.material.emissiveIntensity = 0.2 + Math.sin(time * 2) * 0.1;
    robot.panel2.material.emissiveIntensity = 0.2 + Math.sin(time * 2 + 1) * 0.1;
  }

  // Slime particles dripping
  if (slimeParticles) {
    const pos = slimeParticles.geometry.attributes.position.array;
    const vel = slimeParticles.userData.velocities;

    for (let i = 0; i < pos.length / 3; i++) {
      pos[i * 3]     += vel[i * 3];
      pos[i * 3 + 1] += vel[i * 3 + 1];
      pos[i * 3 + 2] += vel[i * 3 + 2];

      // Reset when particle falls too far
      if (pos[i * 3 + 1] < -8) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const r = 2 + Math.random() * 0.5;

        pos[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
        pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 1.3;
        pos[i * 3 + 2] = r * Math.cos(phi) * 0.9;

        vel[i * 3]     = (Math.random() - 0.5) * 0.02;
        vel[i * 3 + 1] = -0.02 - Math.random() * 0.03;
        vel[i * 3 + 2] = (Math.random() - 0.5) * 0.02;
      }
    }

    slimeParticles.geometry.attributes.position.needsUpdate = true;
  }

  // Energy field orbiting
  if (energyField) {
    const pos = energyField.geometry.attributes.position.array;
    const meta = energyField.userData.meta;

    for (let i = 0; i < meta.length; i++) {
      const m = meta[i];
      const t = time * m.speed + m.offset;
      const theta = m.theta + t * 0.5;
      const phi = m.phi + Math.sin(t * 0.3) * 0.2;

      pos[i * 3]     = m.radius * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = m.radius * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = m.radius * Math.cos(phi);
    }

    energyField.geometry.attributes.position.needsUpdate = true;
  }

  // Slow star rotation
  if (stars) {
    stars.rotation.y = time * 0.01;
  }

  // Nebula drift
  if (nebula) {
    nebula.rotation.y = time * 0.005;
    nebula.rotation.x = Math.sin(time * 0.01) * 0.1;
  }

  // Camera gentle movement
  camera.position.x = Math.sin(time * 0.1) * 2;
  camera.position.y = 2 + Math.sin(time * 0.15) * 1;
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
  if (!robot) return;

  const eyeColor = new THREE.Color();
  let tipColor = new THREE.Color(0xff0088);

  switch (state) {
    case 'thinking':
      eyeColor.setHex(0xffff00); // Yellow
      tipColor.setHex(0xffff00);
      break;

    case 'speaking':
      eyeColor.setHex(0x00ff88); // Green
      tipColor.setHex(0x00ff88);
      break;

    case 'active':
      eyeColor.setHex(0x00ffff); // Cyan
      tipColor.setHex(0x00ffff);
      break;

    default: // standby
      eyeColor.setHex(0x00ffff); // Cyan
      tipColor.setHex(0xff0088); // Pink
  }

  robot.leftEye.material.color.copy(eyeColor);
  robot.leftEye.material.emissive.copy(eyeColor);
  robot.rightEye.material.color.copy(eyeColor);
  robot.rightEye.material.emissive.copy(eyeColor);
  robot.leftGlow.material.color.copy(eyeColor);
  robot.rightGlow.material.color.copy(eyeColor);
  robot.tip.material.color.copy(tipColor);
  robot.tip.material.emissive.copy(tipColor);
}

// Initialize
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initScene);
} else {
  initScene();
}
