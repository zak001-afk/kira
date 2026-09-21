// ═══════════════════════════════════════════════════════════════
// KIRA 3D Human Face - Three.js Implementation
// ═══════════════════════════════════════════════════════════════

let scene, camera, renderer;
let head, eyes = [], lips, nose, eyebrows = [], rings = [], particles;
let clock = new THREE.Clock();

// ═══════════════════════════════════════════════════════════════
// Scene Setup
// ═══════════════════════════════════════════════════════════════

function initScene() {
  // Scene
  scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x0a0e27, 0.012);

  // Camera
  camera = new THREE.PerspectiveCamera(
    60,
    window.innerWidth / window.innerHeight,
    0.1,
    1000
  );
  camera.position.set(0, 1, 8);
  camera.lookAt(0, 0, 0);

  // Renderer
  const canvas = document.getElementById('scene');
  renderer = new THREE.WebGLRenderer({
    canvas: canvas,
    antialias: true,
    alpha: true
  });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.2;

  // Lighting - More natural for human face
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
  scene.add(ambientLight);

  const keyLight = new THREE.DirectionalLight(0xffffff, 1);
  keyLight.position.set(5, 5, 5);
  scene.add(keyLight);

  const fillLight = new THREE.DirectionalLight(0x00d4ff, 0.5);
  fillLight.position.set(-5, 0, 5);
  scene.add(fillLight);

  const rimLight = new THREE.DirectionalLight(0x0066ff, 0.8);
  rimLight.position.set(0, 5, -5);
  scene.add(rimLight);

  const bottomLight = new THREE.PointLight(0x00d4ff, 0.5, 20);
  bottomLight.position.set(0, -3, 3);
  scene.add(bottomLight);

  // Create objects
  createHead();
  createNose();
  createEyes();
  createEyebrows();
  createLips();
  createRings();
  createParticles();
  createGrid();

  // Handle resize
  window.addEventListener('resize', onWindowResize);

  // Start animation
  animate();
}

// ═══════════════════════════════════════════════════════════════
// Human Head
// ═══════════════════════════════════════════════════════════════

function createHead() {
  // Main head shape - more realistic human proportions
  const headGeometry = new THREE.SphereGeometry(2, 64, 64);
  const positions = headGeometry.attributes.position;
  
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i);
    const y = positions.getY(i);
    const z = positions.getZ(i);
    
    // Create more human-like head shape
    // Elongate vertically
    positions.setY(i, y * 1.25);
    
    // Narrow the sides slightly
    positions.setX(i, x * 0.92);
    
    // Create jaw/chin
    if (y < -0.3) {
      const factor = 1 - Math.abs(y + 0.3) * 0.4;
      positions.setX(i, x * factor);
      positions.setZ(i, z * Math.max(0.7, factor));
    }
    
    // Flatten the back of head slightly
    if (z < -0.5) {
      positions.setZ(i, z * 0.85);
    }
    
    // Create forehead
    if (y > 1.0 && z > 0) {
      positions.setZ(i, z * 1.1);
    }
  }
  
  headGeometry.computeVertexNormals();

  // Skin-like material with subtle AI glow
  const headMaterial = new THREE.MeshPhysicalMaterial({
    color: 0xd4e4f4,  // Pale blue-white skin tone
    emissive: 0x001133,
    emissiveIntensity: 0.2,
    metalness: 0.1,
    roughness: 0.6,
    clearcoat: 0.3,
    clearcoatRoughness: 0.4,
    sheen: 0.5,
    sheenRoughness: 0.8,
    sheenColor: new THREE.Color(0x00d4ff)
  });

  head = new THREE.Mesh(headGeometry, headMaterial);
  scene.add(head);

  // Add subtle subsurface scattering effect with inner glow
  const innerGlowGeometry = new THREE.SphereGeometry(1.95, 32, 32);
  const innerGlowMaterial = new THREE.MeshBasicMaterial({
    color: 0x00d4ff,
    transparent: true,
    opacity: 0.05,
    side: THREE.BackSide
  });
  const innerGlow = new THREE.Mesh(innerGlowGeometry, innerGlowMaterial);
  head.add(innerGlow);
}

// ═══════════════════════════════════════════════════════════════
// Nose
// ═══════════════════════════════════════════════════════════════

function createNose() {
  // Nose bridge
  const bridgeGeometry = new THREE.CylinderGeometry(0.12, 0.18, 0.8, 16);
  const noseMaterial = new THREE.MeshPhysicalMaterial({
    color: 0xd4e4f4,
    emissive: 0x001133,
    emissiveIntensity: 0.2,
    metalness: 0.1,
    roughness: 0.6
  });
  
  nose = new THREE.Mesh(bridgeGeometry, noseMaterial);
  nose.position.set(0, -0.1, 1.9);
  nose.rotation.x = Math.PI / 2;
  head.add(nose);

  // Nose tip
  const tipGeometry = new THREE.SphereGeometry(0.2, 16, 16);
  const tip = new THREE.Mesh(tipGeometry, noseMaterial);
  tip.position.set(0, -0.5, 2.0);
  tip.scale.set(1, 0.8, 1.2);
  head.add(tip);
}

// ═══════════════════════════════════════════════════════════════
// Eyes
// ═══════════════════════════════════════════════════════════════

function createEyes() {
  const eyePositions = [
    { x: -0.55, y: 0.35, z: 1.75 },  // Left eye
    { x: 0.55, y: 0.35, z: 1.75 }    // Right eye
  ];

  eyePositions.forEach((pos, index) => {
    // Eye socket (slight indentation)
    const socketGeometry = new THREE.SphereGeometry(0.38, 32, 32);
    const socketMaterial = new THREE.MeshPhysicalMaterial({
      color: 0xb8c8d8,  // Slightly darker
      metalness: 0.1,
      roughness: 0.7
    });
    const socket = new THREE.Mesh(socketGeometry, socketMaterial);
    socket.position.set(pos.x, pos.y, pos.z - 0.1);
    socket.scale.set(1, 0.75, 0.6);
    head.add(socket);

    // Eyeball (white)
    const eyeballGeometry = new THREE.SphereGeometry(0.28, 32, 32);
    const eyeballMaterial = new THREE.MeshPhysicalMaterial({
      color: 0xffffff,
      metalness: 0,
      roughness: 0.3,
      clearcoat: 1,
      clearcoatRoughness: 0.1
    });
    const eyeball = new THREE.Mesh(eyeballGeometry, eyeballMaterial);
    eyeball.position.set(pos.x, pos.y, pos.z);
    eyeball.scale.set(1, 0.75, 0.6);
    head.add(eyeball);

    // Iris (colored part)
    const irisGeometry = new THREE.SphereGeometry(0.15, 32, 32);
    const irisMaterial = new THREE.MeshBasicMaterial({
      color: 0x00d4ff,
      transparent: true,
      opacity: 0.95
    });
    const iris = new THREE.Mesh(irisGeometry, irisMaterial);
    iris.position.set(pos.x, pos.y, pos.z + 0.15);
    iris.scale.set(1, 0.75, 0.4);
    head.add(iris);
    eyes.push(iris);

    // Pupil (black center)
    const pupilGeometry = new THREE.SphereGeometry(0.08, 16, 16);
    const pupilMaterial = new THREE.MeshBasicMaterial({
      color: 0x000000
    });
    const pupil = new THREE.Mesh(pupilGeometry, pupilMaterial);
    pupil.position.set(pos.x, pos.y, pos.z + 0.18);
    pupil.scale.set(1, 0.75, 0.4);
    head.add(pupil);

    // Eye glow effect
    const glowGeometry = new THREE.SphereGeometry(0.2, 16, 16);
    const glowMaterial = new THREE.MeshBasicMaterial({
      color: 0x00d4ff,
      transparent: true,
      opacity: 0.3,
      blending: THREE.AdditiveBlending
    });
    const glow = new THREE.Mesh(glowGeometry, glowMaterial);
    glow.position.set(pos.x, pos.y, pos.z + 0.1);
    glow.scale.set(1, 0.75, 0.5);
    head.add(glow);
    iris.userData.glow = glow;
  });
}

// ═══════════════════════════════════════════════════════════════
// Eyebrows
// ═══════════════════════════════════════════════════════════════

function createEyebrows() {
  const eyebrowPositions = [
    { x: -0.55, y: 0.75, z: 1.7, rotation: -0.2 },  // Left eyebrow
    { x: 0.55, y: 0.75, z: 1.7, rotation: 0.2 }    // Right eyebrow
  ];

  eyebrowPositions.forEach((pos) => {
    const eyebrowGeometry = new THREE.BoxGeometry(0.5, 0.08, 0.1);
    const eyebrowMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x8899aa,
      metalness: 0.2,
      roughness: 0.5
    });
    
    const eyebrow = new THREE.Mesh(eyebrowGeometry, eyebrowMaterial);
    eyebrow.position.set(pos.x, pos.y, pos.z);
    eyebrow.rotation.z = pos.rotation;
    head.add(eyebrow);
    eyebrows.push(eyebrow);
  });
}

// ═══════════════════════════════════════════════════════════════
// Lips
// ═══════════════════════════════════════════════════════════════

function createLips() {
  // Upper lip
  const upperLipGeometry = new THREE.TorusGeometry(0.3, 0.08, 16, 32, Math.PI);
  const lipMaterial = new THREE.MeshPhysicalMaterial({
    color: 0xcc8899,  // Soft pink
    emissive: 0x001122,
    emissiveIntensity: 0.1,
    metalness: 0.1,
    roughness: 0.4,
    clearcoat: 0.6,
    clearcoatRoughness: 0.3
  });
  
  const upperLip = new THREE.Mesh(upperLipGeometry, lipMaterial);
  upperLip.position.set(0, -0.85, 1.85);
  upperLip.rotation.x = Math.PI;
  upperLip.scale.set(1, 0.5, 1);
  head.add(upperLip);

  // Lower lip
  const lowerLipGeometry = new THREE.TorusGeometry(0.32, 0.1, 16, 32, Math.PI);
  const lowerLip = new THREE.Mesh(lowerLipGeometry, lipMaterial);
  lowerLip.position.set(0, -0.95, 1.85);
  lowerLip.scale.set(1, 0.6, 1);
  head.add(lowerLip);

  // Store reference for animation
  lips = { upper: upperLip, lower: lowerLip };
}

// ═══════════════════════════════════════════════════════════════
// Orbital Rings (subtle, around head)
// ═══════════════════════════════════════════════════════════════

function createRings() {
  const ringConfigs = [
    { radius: 3.5, tube: 0.015, rotation: [0, 0, Math.PI / 6], speed: 0.3, color: 0x00d4ff, opacity: 0.3 },
    { radius: 4, tube: 0.01, rotation: [Math.PI / 4, 0, 0], speed: -0.2, color: 0x0099cc, opacity: 0.2 },
  ];

  ringConfigs.forEach(config => {
    const geometry = new THREE.TorusGeometry(config.radius, config.tube, 16, 100);
    const material = new THREE.MeshBasicMaterial({
      color: config.color,
      transparent: true,
      opacity: config.opacity
    });

    const ring = new THREE.Mesh(geometry, material);
    ring.rotation.set(...config.rotation);
    ring.userData.speed = config.speed;
    
    scene.add(ring);
    rings.push(ring);
  });
}

// ═══════════════════════════════════════════════════════════════
// Particle System
// ═══════════════════════════════════════════════════════════════

function createParticles() {
  const particleCount = 1500;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(particleCount * 3);
  const colors = new Float32Array(particleCount * 3);

  const color = new THREE.Color();

  for (let i = 0; i < particleCount; i++) {
    const radius = 6 + Math.random() * 15;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);

    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = radius * Math.cos(phi);

    const hue = 0.5 + Math.random() * 0.2;
    color.setHSL(hue, 1.0, 0.5);
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  const material = new THREE.PointsMaterial({
    size: 0.08,
    vertexColors: true,
    transparent: true,
    opacity: 0.5,
    blending: THREE.AdditiveBlending
  });

  particles = new THREE.Points(geometry, material);
  scene.add(particles);
}

// ═══════════════════════════════════════════════════════════════
// Grid Floor
// ═══════════════════════════════════════════════════════════════

function createGrid() {
  const gridHelper = new THREE.GridHelper(50, 50, 0x00d4ff, 0x003366);
  gridHelper.position.y = -4;
  gridHelper.material.opacity = 0.15;
  gridHelper.material.transparent = true;
  scene.add(gridHelper);
}

// ═══════════════════════════════════════════════════════════════
// Animation Loop
// ═══════════════════════════════════════════════════════════════

function animate() {
  requestAnimationFrame(animate);

  const time = clock.getElapsedTime();

  // Head natural movement
  if (head) {
    head.rotation.y = Math.sin(time * 0.3) * 0.12;
    head.rotation.x = Math.sin(time * 0.2) * 0.04;
    head.position.y = Math.sin(time * 0.5) * 0.08;
  }

  // Eye tracking (subtle movement)
  eyes.forEach(eye => {
    const trackX = Math.sin(time * 0.4) * 0.02;
    const trackY = Math.sin(time * 0.3) * 0.01;
    eye.position.x += trackX;
    eye.position.y += trackY;
    
    if (eye.userData.glow) {
      eye.userData.glow.position.x = eye.position.x;
      eye.userData.glow.position.y = eye.position.y;
    }
  });

  // Eyebrow subtle movement
  eyebrows.forEach((eyebrow, index) => {
    const lift = Math.sin(time * 0.5 + index) * 0.02;
    eyebrow.position.y = 0.75 + lift;
  });

  // Rotate rings
  rings.forEach(ring => {
    ring.rotation.z += ring.userData.speed * 0.01;
    ring.rotation.x += ring.userData.speed * 0.005;
  });

  // Rotate particles
  if (particles) {
    particles.rotation.y = time * 0.03;
    particles.rotation.x = Math.sin(time * 0.1) * 0.1;
  }

  // Camera gentle movement
  camera.position.x = Math.sin(time * 0.1) * 0.3;
  camera.position.y = 1 + Math.sin(time * 0.15) * 0.2;
  camera.lookAt(0, 0, 0);

  renderer.render(scene, camera);
}

// ═══════════════════════════════════════════════════════════════
// Window Resize Handler
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
  if (!head || !eyes.length) return;

  const eyeColor = new THREE.Color();
  let lipSeparation = 0;

  switch(state) {
    case 'thinking':
      eyeColor.setHex(0xffaa00);
      head.material.emissive.setHex(0x332200);
      head.material.emissiveIntensity = 0.3;
      // Eyebrows slightly raised
      eyebrows.forEach(eb => eb.position.y = 0.78);
      break;
      
    case 'speaking':
      eyeColor.setHex(0x00ffaa);
      head.material.emissive.setHex(0x003322);
      head.material.emissiveIntensity = 0.4;
      // Lips animate (separate slightly)
      lipSeparation = 0.05 + Math.sin(Date.now() * 0.015) * 0.03;
      eyebrows.forEach(eb => eb.position.y = 0.75);
      break;
      
    case 'active':
      eyeColor.setHex(0x00ff88);
      head.material.emissive.setHex(0x002211);
      head.material.emissiveIntensity = 0.3;
      eyebrows.forEach(eb => eb.position.y = 0.76);
      break;
      
    default: // standby
      eyeColor.setHex(0x00d4ff);
      head.material.emissive.setHex(0x001133);
      head.material.emissiveIntensity = 0.2;
      eyebrows.forEach(eb => eb.position.y = 0.75);
  }

  // Update eye colors
  eyes.forEach(eye => {
    eye.material.color.copy(eyeColor);
    if (eye.userData.glow) {
      eye.userData.glow.material.color.copy(eyeColor);
    }
  });

  // Update lips for speaking
  if (lips) {
    lips.upper.position.y = -0.85 - lipSeparation;
    lips.lower.position.y = -0.95 + lipSeparation;
  }
}

// Initialize scene when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initScene);
} else {
  initScene();
}
