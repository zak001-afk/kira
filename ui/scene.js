// ═══════════════════════════════════════════════════════════════
// KIRA — Realistic Human Face with Matrix Skin
// Complete rewrite for best visual result
// ═══════════════════════════════════════════════════════════════

let scene, camera, renderer;
let head, eyes = [], lips, nose, eyebrows = [];
let digitalRain, skinCircuits, dataParticles, hairMesh;
let clock = new THREE.Clock();
let currentActivity = 'standby';
let blinkTimer = 0;
let nextBlink = 3 + Math.random() * 4;
let isBlinking = false;
let blinkProgress = 0;

// ═══════════════════════════════════════════════════════════════
// Scene Setup
// ═══════════════════════════════════════════════════════════════

function initScene() {
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x000000);
  scene.fog = new THREE.FogExp2(0x000800, 0.008);

  camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 1000);
  camera.position.set(0, 0.5, 7.5);
  camera.lookAt(0, 0, 0);

  const canvas = document.getElementById('scene');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.3;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  setupLighting();
  createDigitalRain();
  createHead();
  createEars();
  createNose();
  createEyes();
  createEyebrows();
  createLips();
  createHair();
  createSkinCircuits();
  createDataParticles();
  createGrid();

  window.addEventListener('resize', onWindowResize);
  animate();
}

// ═══════════════════════════════════════════════════════════════
// Professional Lighting
// ═══════════════════════════════════════════════════════════════

function setupLighting() {
  // Ambient
  scene.add(new THREE.AmbientLight(0xffffff, 0.4));

  // Key light (main)
  const key = new THREE.DirectionalLight(0xfff5ee, 1.3);
  key.position.set(4, 5, 6);
  key.castShadow = true;
  scene.add(key);

  // Fill light (soft blue)
  const fill = new THREE.DirectionalLight(0x8899bb, 0.5);
  fill.position.set(-5, 2, 4);
  scene.add(fill);

  // Rim light (Matrix green for edge highlight)
  const rim = new THREE.DirectionalLight(0x00ff41, 0.7);
  rim.position.set(0, 3, -6);
  scene.add(rim);

  // Bottom fill (subtle green uplight)
  const bottom = new THREE.PointLight(0x00ff41, 0.25, 15);
  bottom.position.set(0, -4, 3);
  scene.add(bottom);

  // Side accent
  const side = new THREE.PointLight(0x00cc33, 0.3, 12);
  side.position.set(-4, 0, 2);
  scene.add(side);
}

// ═══════════════════════════════════════════════════════════════
// Digital Rain
// ═══════════════════════════════════════════════════════════════

function createDigitalRain() {
  const count = 3000;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const vel = new Float32Array(count);
  const sizes = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    pos[i * 3]     = (Math.random() - 0.5) * 70;
    pos[i * 3 + 1] = Math.random() * 50 - 15;
    pos[i * 3 + 2] = -5 - Math.random() * 40;
    vel[i] = 0.04 + Math.random() * 0.15;
    sizes[i] = 0.05 + Math.random() * 0.1;
  }

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));

  digitalRain = new THREE.Points(geo, new THREE.PointsMaterial({
    color: 0x00ff41,
    size: 0.08,
    transparent: true,
    opacity: 0.35,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true
  }));
  digitalRain.userData.velocities = vel;
  scene.add(digitalRain);
}

// ═══════════════════════════════════════════════════════════════
// Skin Material
// ═══════════════════════════════════════════════════════════════

function createSkinMaterial() {
  return new THREE.MeshPhysicalMaterial({
    color: 0xf5c6a0,
    emissive: 0x000000,
    emissiveIntensity: 0,
    metalness: 0.0,
    roughness: 0.65,
    clearcoat: 0.15,
    clearcoatRoughness: 0.5,
    sheen: 0.8,
    sheenRoughness: 0.4,
    sheenColor: new THREE.Color(0xff9977),
  });
}

// ═══════════════════════════════════════════════════════════════
// Human Head
// ═══════════════════════════════════════════════════════════════

function createHead() {
  const geo = new THREE.SphereGeometry(2, 80, 80);
  const p = geo.attributes.position;

  for (let i = 0; i < p.count; i++) {
    let x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const ny = y / 2;

    // Vertical elongation
    y *= 1.28;

    // Narrow sides
    x *= 0.90;

    // Forehead: slightly wider and more prominent
    if (ny > 0.5 && z > 0) {
      z *= 1.08;
      x *= 1.02;
    }

    // Cheekbones
    if (ny > -0.2 && ny < 0.2 && Math.abs(x) > 1.0 && z > 0.3) {
      x *= 1.08;
      z *= 1.04;
    }

    // Jaw taper
    if (ny < -0.2) {
      const t = Math.min(1, Math.abs(ny + 0.2) * 1.2);
      x *= 1 - t * 0.45;
      z *= 1 - t * 0.25;
    }

    // Chin
    if (ny < -0.7 && z > 0.3) {
      z *= 1.05;
    }

    // Back of head flatter
    if (z < -0.5) z *= 0.82;

    // Eye socket depressions
    const leye = Math.sqrt((x + 0.55) ** 2 + (y / 1.28 - 0.35) ** 2);
    const reye = Math.sqrt((x - 0.55) ** 2 + (y / 1.28 - 0.35) ** 2);
    if (leye < 0.4 && z > 1.0) z -= (0.4 - leye) * 0.3;
    if (reye < 0.4 && z > 1.0) z -= (0.4 - reye) * 0.3;

    // Nose bridge area
    if (Math.abs(x) < 0.2 && ny > -0.3 && ny < 0.2 && z > 1.2) {
      z += 0.15;
    }

    p.setXYZ(i, x, y, z);
  }

  geo.computeVertexNormals();
  head = new THREE.Mesh(geo, createSkinMaterial());
  scene.add(head);
}

// ═══════════════════════════════════════════════════════════════
// Ears
// ═══════════════════════════════════════════════════════════════

function createEars() {
  const earGeo = new THREE.SphereGeometry(0.3, 16, 16);
  const skinMat = createSkinMaterial();

  [-1, 1].forEach(side => {
    const ear = new THREE.Mesh(earGeo, skinMat);
    ear.position.set(side * 1.75, 0.1, 0.2);
    ear.scale.set(0.5, 1.2, 0.8);
    head.add(ear);
  });
}

// ═══════════════════════════════════════════════════════════════
// Nose
// ═══════════════════════════════════════════════════════════════

function createNose() {
  const skinMat = createSkinMaterial();

  // Bridge
  const bridge = new THREE.Mesh(
    new THREE.CylinderGeometry(0.10, 0.16, 0.9, 16),
    skinMat
  );
  bridge.position.set(0, -0.05, 1.95);
  bridge.rotation.x = Math.PI / 2;
  head.add(bridge);

  // Tip
  const tip = new THREE.Mesh(new THREE.SphereGeometry(0.18, 16, 16), skinMat);
  tip.position.set(0, -0.48, 2.08);
  tip.scale.set(1.1, 0.75, 1.15);
  head.add(tip);

  // Nostrils
  [-1, 1].forEach(side => {
    const nostril = new THREE.Mesh(new THREE.SphereGeometry(0.08, 12, 12), skinMat);
    nostril.position.set(side * 0.12, -0.52, 2.0);
    head.add(nostril);
  });

  nose = bridge;
}

// ═══════════════════════════════════════════════════════════════
// Eyes (detailed)
// ═══════════════════════════════════════════════════════════════

function createEyes() {
  const positions = [
    { x: -0.55, y: 0.38, z: 1.72 },
    { x:  0.55, y: 0.38, z: 1.72 }
  ];

  positions.forEach(pos => {
    // Eyelid (skin-colored cover for blinking)
    const lidGeo = new THREE.SphereGeometry(0.34, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2);
    const lid = new THREE.Mesh(lidGeo, createSkinMaterial());
    lid.position.set(pos.x, pos.y, pos.z - 0.05);
    lid.scale.set(1, 0.75, 0.6);
    lid.rotation.x = Math.PI;
    lid.visible = false;
    head.add(lid);

    // Eyeball
    const eyeball = new THREE.Mesh(
      new THREE.SphereGeometry(0.28, 32, 32),
      new THREE.MeshPhysicalMaterial({
        color: 0xfafafa,
        metalness: 0,
        roughness: 0.15,
        clearcoat: 1,
        clearcoatRoughness: 0.05
      })
    );
    eyeball.position.set(pos.x, pos.y, pos.z);
    eyeball.scale.set(1, 0.72, 0.6);
    head.add(eyeball);

    // Limbal ring (dark ring around iris)
    const limbal = new THREE.Mesh(
      new THREE.SphereGeometry(0.175, 32, 32),
      new THREE.MeshBasicMaterial({ color: 0x003311, transparent: true, opacity: 0.9 })
    );
    limbal.position.set(pos.x, pos.y, pos.z + 0.14);
    limbal.scale.set(1, 0.72, 0.4);
    head.add(limbal);

    // Iris (Matrix green)
    const iris = new THREE.Mesh(
      new THREE.SphereGeometry(0.155, 32, 32),
      new THREE.MeshBasicMaterial({ color: 0x00ff41, transparent: true, opacity: 0.95 })
    );
    iris.position.set(pos.x, pos.y, pos.z + 0.15);
    iris.scale.set(1, 0.72, 0.4);
    head.add(iris);
    eyes.push(iris);

    // Pupil
    const pupil = new THREE.Mesh(
      new THREE.SphereGeometry(0.07, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0x000000 })
    );
    pupil.position.set(pos.x, pos.y, pos.z + 0.19);
    pupil.scale.set(1, 0.72, 0.4);
    head.add(pupil);

    // Light reflection on eye
    const reflection = new THREE.Mesh(
      new THREE.SphereGeometry(0.03, 8, 8),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.8 })
    );
    reflection.position.set(pos.x + 0.05, pos.y + 0.05, pos.z + 0.22);
    head.add(reflection);

    // Glow
    const glow = new THREE.Mesh(
      new THREE.SphereGeometry(0.24, 16, 16),
      new THREE.MeshBasicMaterial({
        color: 0x00ff41, transparent: true, opacity: 0.25, blending: THREE.AdditiveBlending
      })
    );
    glow.position.set(pos.x, pos.y, pos.z + 0.08);
    glow.scale.set(1, 0.72, 0.5);
    head.add(glow);

    iris.userData.glow = glow;
    iris.userData.lid = lid;
    iris.userData.eyeball = eyeball;
    iris.userData.pupil = pupil;
    iris.userData.reflection = reflection;
    iris.userData.limbal = limbal;
    iris.userData.basePos = { ...pos };
  });
}

// ═══════════════════════════════════════════════════════════════
// Eyebrows
// ═══════════════════════════════════════════════════════════════

function createEyebrows() {
  const configs = [
    { x: -0.55, y: 0.78, z: 1.68, rz: -0.15 },
    { x:  0.55, y: 0.78, z: 1.68, rz:  0.15 }
  ];

  configs.forEach(c => {
    // Use multiple small segments for a more natural brow
    const group = new THREE.Group();
    const mat = new THREE.MeshPhysicalMaterial({ color: 0x2a1a10, roughness: 0.8 });

    for (let i = 0; i < 5; i++) {
      const seg = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.06, 0.08), mat);
      seg.position.x = (i - 2) * 0.11;
      seg.position.y = -Math.abs(i - 2) * 0.02;
      group.add(seg);
    }

    group.position.set(c.x, c.y, c.z);
    group.rotation.z = c.rz;
    head.add(group);
    eyebrows.push(group);
  });
}

// ═══════════════════════════════════════════════════════════════
// Lips
// ═══════════════════════════════════════════════════════════════

function createLips() {
  const lipMat = new THREE.MeshPhysicalMaterial({
    color: 0xcc7777,
    metalness: 0,
    roughness: 0.25,
    clearcoat: 0.9,
    clearcoatRoughness: 0.15
  });

  // Upper lip
  const upper = new THREE.Mesh(
    new THREE.TorusGeometry(0.28, 0.07, 16, 32, Math.PI),
    lipMat
  );
  upper.position.set(0, -0.87, 1.88);
  upper.rotation.x = Math.PI;
  upper.scale.set(1, 0.5, 1);
  head.add(upper);

  // Lower lip
  const lower = new THREE.Mesh(
    new THREE.TorusGeometry(0.30, 0.09, 16, 32, Math.PI),
    lipMat
  );
  lower.position.set(0, -0.97, 1.88);
  lower.scale.set(1, 0.55, 1);
  head.add(lower);

  // Mouth line (dark gap)
  const line = new THREE.Mesh(
    new THREE.BoxGeometry(0.55, 0.015, 0.05),
    new THREE.MeshBasicMaterial({ color: 0x331111 })
  );
  line.position.set(0, -0.92, 1.92);
  head.add(line);

  lips = { upper, lower, line, baseUpperY: -0.87, baseLowerY: -0.97 };
}

// ═══════════════════════════════════════════════════════════════
// Hair
// ═══════════════════════════════════════════════════════════════

function createHair() {
  const hairGeo = new THREE.SphereGeometry(2.08, 64, 64);
  const p = hairGeo.attributes.position;

  for (let i = 0; i < p.count; i++) {
    let x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const ny = y / 2;

    // Only keep top and sides of hair
    if (ny < 0.15 && z > 0.5) {
      p.setXYZ(i, 0, 0, 0);
      continue;
    }

    // Shape hair
    y *= 1.3;
    x *= 0.95;

    if (z < -0.3) z *= 0.88;
    if (ny > 0.5) { y *= 1.05; z *= 1.05; }

    p.setXYZ(i, x, y, z);
  }

  hairGeo.computeVertexNormals();

  hairMesh = new THREE.Mesh(hairGeo, new THREE.MeshPhysicalMaterial({
    color: 0x1a0f08,
    metalness: 0.3,
    roughness: 0.4,
    clearcoat: 0.6,
    clearcoatRoughness: 0.2,
    sheen: 1,
    sheenRoughness: 0.3,
    sheenColor: new THREE.Color(0x332211)
  }));

  head.add(hairMesh);
}

// ═══════════════════════════════════════════════════════════════
// Matrix Skin Circuits
// ═══════════════════════════════════════════════════════════════

function createSkinCircuits() {
  skinCircuits = new THREE.Group();

  const lineMat = new THREE.LineBasicMaterial({
    color: 0x00ff41, transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending
  });

  const circuits = [
    // Forehead
    [[-0.7, 1.5, 1.45], [-0.4, 1.55, 1.55], [0, 1.6, 1.58], [0.4, 1.55, 1.55], [0.7, 1.5, 1.45]],
    [[-0.5, 1.3, 1.55], [-0.25, 1.35, 1.6], [0.25, 1.35, 1.6], [0.5, 1.3, 1.55]],
    [[-0.3, 1.15, 1.62], [0, 1.2, 1.65], [0.3, 1.15, 1.62]],

    // Temples
    [[-1.55, 0.8, 0.85], [-1.6, 0.5, 0.78], [-1.55, 0.2, 0.72], [-1.5, -0.1, 0.65]],
    [[1.55, 0.8, 0.85], [1.6, 0.5, 0.78], [1.55, 0.2, 0.72], [1.5, -0.1, 0.65]],

    // Cheeks
    [[-1.25, 0.0, 1.35], [-1.3, -0.3, 1.28], [-1.25, -0.6, 1.18]],
    [[1.25, 0.0, 1.35], [1.3, -0.3, 1.28], [1.25, -0.6, 1.18]],

    // Jaw
    [[-0.7, -1.3, 1.25], [-0.35, -1.5, 1.35], [0, -1.6, 1.42], [0.35, -1.5, 1.35], [0.7, -1.3, 1.25]],

    // Nose bridge accent
    [[-0.15, 0.2, 1.95], [0, 0.0, 2.0], [0.15, 0.2, 1.95]],

    // Under-eye accents
    [[-0.75, 0.15, 1.65], [-0.55, 0.08, 1.7], [-0.35, 0.15, 1.65]],
    [[0.75, 0.15, 1.65], [0.55, 0.08, 1.7], [0.35, 0.15, 1.65]],
  ];

  circuits.forEach(pts => {
    const points = pts.map(p => new THREE.Vector3(...p));
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    skinCircuits.add(new THREE.Line(geo, lineMat.clone()));
  });

  // Nodes
  const nodeMat = new THREE.MeshBasicMaterial({
    color: 0x00ff88, transparent: true, opacity: 0.85
  });

  const nodes = [
    [-0.7, 1.5, 1.45], [0.7, 1.5, 1.45], [0, 1.6, 1.58],
    [-1.55, 0.8, 0.85], [1.55, 0.8, 0.85],
    [-1.25, 0.0, 1.35], [1.25, 0.0, 1.35],
    [-0.7, -1.3, 1.25], [0.7, -1.3, 1.25], [0, -1.6, 1.42],
    [-0.55, 0.08, 1.7], [0.55, 0.08, 1.7],
    [0, 0.0, 2.0]
  ];

  nodes.forEach(pos => {
    const node = new THREE.Mesh(new THREE.SphereGeometry(0.035, 8, 8), nodeMat.clone());
    node.position.set(...pos);
    skinCircuits.add(node);
  });

  scene.add(skinCircuits);
}

// ═══════════════════════════════════════════════════════════════
// Data Particles (flow along circuits)
// ═══════════════════════════════════════════════════════════════

function createDataParticles() {
  const count = 200;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const meta = [];

  for (let i = 0; i < count; i++) {
    // Random position near the face surface
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const r = 2 + Math.random() * 0.5;

    pos[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 1.28;
    pos[i * 3 + 2] = r * Math.cos(phi);

    meta.push({
      theta, phi, r,
      speed: 0.2 + Math.random() * 0.5,
      offset: Math.random() * Math.PI * 2
    });
  }

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));

  dataParticles = new THREE.Points(geo, new THREE.PointsMaterial({
    color: 0x00ff88,
    size: 0.06,
    transparent: true,
    opacity: 0.8,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true
  }));
  dataParticles.userData.meta = meta;
  scene.add(dataParticles);
}

// ═══════════════════════════════════════════════════════════════
// Grid Floor
// ═══════════════════════════════════════════════════════════════

function createGrid() {
  const grid = new THREE.GridHelper(80, 80, 0x00ff41, 0x003300);
  grid.position.y = -4.5;
  grid.material.opacity = 0.12;
  grid.material.transparent = true;
  scene.add(grid);
}

// ═══════════════════════════════════════════════════════════════
// Blink Animation
// ═══════════════════════════════════════════════════════════════

function updateBlink(dt) {
  blinkTimer += dt;

  if (!isBlinking && blinkTimer >= nextBlink) {
    isBlinking = true;
    blinkProgress = 0;
    blinkTimer = 0;
    nextBlink = 2.5 + Math.random() * 5;
  }

  if (isBlinking) {
    blinkProgress += dt * 8; // Speed of blink

    if (blinkProgress >= 2) {
      isBlinking = false;
      blinkProgress = 0;
      eyes.forEach(eye => {
        if (eye.userData.lid) eye.userData.lid.visible = false;
        if (eye.userData.eyeball) eye.userData.eyeball.visible = true;
      });
      return;
    }

    // Blink curve: close then open
    const t = blinkProgress < 1 ? blinkProgress : 2 - blinkProgress;

    eyes.forEach(eye => {
      if (eye.userData.lid) {
        eye.userData.lid.visible = true;
        eye.userData.lid.scale.y = 0.75 * t;
      }
      if (eye.userData.eyeball) {
        eye.userData.eyeball.visible = t < 0.8;
      }
    });
  }
}

// ═══════════════════════════════════════════════════════════════
// Animation Loop
// ═══════════════════════════════════════════════════════════════

function animate() {
  requestAnimationFrame(animate);

  const dt = clock.getDelta();
  const time = clock.getElapsedTime();

  // Digital rain
  if (digitalRain) {
    const pos = digitalRain.geometry.attributes.position.array;
    const vel = digitalRain.userData.velocities;
    for (let i = 0; i < pos.length / 3; i++) {
      pos[i * 3 + 1] -= vel[i];
      if (pos[i * 3 + 1] < -15) {
        pos[i * 3 + 1] = 35;
        pos[i * 3]     = (Math.random() - 0.5) * 70;
        pos[i * 3 + 2] = -5 - Math.random() * 40;
      }
    }
    digitalRain.geometry.attributes.position.needsUpdate = true;
  }

  // Head breathing + subtle movement
  if (head) {
    const breathe = Math.sin(time * 1.2) * 0.03;
    head.rotation.y = Math.sin(time * 0.25) * 0.1;
    head.rotation.x = Math.sin(time * 0.18) * 0.03 + breathe * 0.1;
    head.position.y = 0 + breathe;
  }

  // Skin circuits follow head
  if (skinCircuits && head) {
    skinCircuits.rotation.copy(head.rotation);
    skinCircuits.position.copy(head.position);

    // Pulse circuit lines
    skinCircuits.children.forEach((child, i) => {
      if (child.material && child.material.opacity !== undefined) {
        const base = child.isLine ? 0.5 : 0.7;
        child.material.opacity = base + Math.sin(time * 3 + i * 0.7) * 0.2;
      }
    });
  }

  // Data particles orbit
  if (dataParticles) {
    const pos = dataParticles.geometry.attributes.position.array;
    const meta = dataParticles.userData.meta;

    for (let i = 0; i < meta.length; i++) {
      const m = meta[i];
      const t = time * m.speed + m.offset;
      const theta = m.theta + t * 0.3;
      const phi = m.phi + Math.sin(t * 0.5) * 0.2;
      const r = m.r + Math.sin(t * 2) * 0.1;

      pos[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 1.28;
      pos[i * 3 + 2] = r * Math.cos(phi);
    }
    dataParticles.geometry.attributes.position.needsUpdate = true;
  }

  // Eye pulsing
  eyes.forEach((eye, i) => {
    const pulse = 1 + Math.sin(time * 2.5 + i) * 0.06;
    eye.scale.set(pulse, pulse * 0.72, pulse * 0.4);
    if (eye.userData.glow) {
      eye.userData.glow.material.opacity = 0.2 + Math.sin(time * 2.5) * 0.1;
    }
  });

  // Eyebrow subtle movement
  eyebrows.forEach((brow, i) => {
    brow.position.y = 0.78 + Math.sin(time * 0.4 + i) * 0.015;
  });

  // Blink
  updateBlink(dt);

  // Camera gentle sway
  camera.position.x = Math.sin(time * 0.08) * 0.25;
  camera.position.y = 0.5 + Math.sin(time * 0.12) * 0.15;
  camera.lookAt(0, 0.2, 0);

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
  if (!head || !eyes.length) return;

  const eyeColor = new THREE.Color();
  let lipSep = 0;
  let circuitBoost = 1;

  switch (state) {
    case 'thinking':
      eyeColor.setHex(0x88ff88);
      circuitBoost = 1.6;
      eyebrows.forEach(eb => { eb.position.y = 0.82; });
      break;

    case 'speaking':
      eyeColor.setHex(0x00ff88);
      circuitBoost = 1.4;
      lipSep = 0.06 + Math.sin(Date.now() * 0.018) * 0.04;
      eyebrows.forEach(eb => { eb.position.y = 0.78; });
      break;

    case 'active':
      eyeColor.setHex(0x00ff41);
      circuitBoost = 1.3;
      eyebrows.forEach(eb => { eb.position.y = 0.79; });
      break;

    default:
      eyeColor.setHex(0x00aa00);
      circuitBoost = 0.9;
      eyebrows.forEach(eb => { eb.position.y = 0.78; });
  }

  eyes.forEach(eye => {
    eye.material.color.copy(eyeColor);
    if (eye.userData.glow) eye.userData.glow.material.color.copy(eyeColor);
  });

  if (lips) {
    lips.upper.position.y = lips.baseUpperY - lipSep;
    lips.lower.position.y = lips.baseLowerY + lipSep;
    lips.line.scale.y = 1 + lipSep * 15;
  }

  if (skinCircuits) {
    skinCircuits.children.forEach(child => {
      if (child.material) {
        const base = child.isLine ? 0.5 : 0.7;
        child.material.opacity = Math.min(1, base * circuitBoost);
      }
    });
  }

  // Speaking: animate lips continuously
  if (state === 'speaking') {
    const animateLips = () => {
      if (currentActivity !== 'speaking') return;
      const t = Date.now() * 0.018;
      const sep = 0.06 + Math.sin(t) * 0.04;
      if (lips) {
        lips.upper.position.y = lips.baseUpperY - sep;
        lips.lower.position.y = lips.baseLowerY + sep;
        lips.line.scale.y = 1 + sep * 15;
      }
      requestAnimationFrame(animateLips);
    };
    animateLips();
  }
}

// Initialize
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initScene);
} else {
  initScene();
}
