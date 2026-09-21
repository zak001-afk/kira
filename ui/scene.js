// ═══════════════════════════════════════════════════════════════
// KIRA 3D Humanoid AI Face - Three.js Implementation
// ═══════════════════════════════════════════════════════════════

let scene, camera, renderer;
let head, eyes = [], mouth, rings = [], particles;
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

  // Lighting
  const ambientLight = new THREE.AmbientLight(0x00d4ff, 0.4);
  scene.add(ambientLight);

  const pointLight1 = new THREE.PointLight(0x00d4ff, 2.5, 50);
  pointLight1.position.set(5, 5, 5);
  scene.add(pointLight1);

  const pointLight2 = new THREE.PointLight(0x0066ff, 2, 50);
  pointLight2.position.set(-5, -3, 5);
  scene.add(pointLight2);

  const pointLight3 = new THREE.PointLight(0x00ffaa, 1.5, 50);
  pointLight3.position.set(0, 5, -5);
  scene.add(pointLight3);

  // Rim light for dramatic effect
  const rimLight = new THREE.DirectionalLight(0x00d4ff, 1);
  rimLight.position.set(-5, 0, -5);
  scene.add(rimLight);

  // Create objects
  createHead();
  createEyes();
  createMouth();
  createRings();
  createParticles();
  createGrid();

  // Handle resize
  window.addEventListener('resize', onWindowResize);

  // Start animation
  animate();
}

// ═══════════════════════════════════════════════════════════════
// 3D Head/Face
// ═══════════════════════════════════════════════════════════════

function createHead() {
  // Main head shape - elongated sphere
  const headGeometry = new THREE.SphereGeometry(2, 64, 64);
  // Modify vertices to create a more head-like shape
  const positions = headGeometry.attributes.position;
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i);
    const y = positions.getY(i);
    const z = positions.getZ(i);
    
    // Elongate vertically and flatten sides slightly
    positions.setY(i, y * 1.2);
    positions.setX(i, x * 0.95);
    
    // Create chin area
    if (y < -0.5) {
      const factor = 1 - Math.abs(y + 0.5) * 0.3;
      positions.setX(i, x * factor);
      positions.setZ(i, z * factor);
    }
  }
  headGeometry.computeVertexNormals();

  const headMaterial = new THREE.MeshPhysicalMaterial({
    color: 0x1a2a4a,
    emissive: 0x001133,
    emissiveIntensity: 0.3,
    metalness: 0.8,
    roughness: 0.2,
    clearcoat: 0.8,
    clearcoatRoughness: 0.1,
    transparent: true,
    opacity: 0.9
  });

  head = new THREE.Mesh(headGeometry, headMaterial);
  scene.add(head);

  // Add circuit patterns on face
  createCircuitPatterns();

  // Inner glow
  const glowGeometry = new THREE.SphereGeometry(2.1, 32, 32);
  const glowMaterial = new THREE.MeshBasicMaterial({
    color: 0x00d4ff,
    transparent: true,
    opacity: 0.1,
    side: THREE.BackSide
  });
  const glow = new THREE.Mesh(glowGeometry, glowMaterial);
  head.add(glow);
}

// ═══════════════════════════════════════════════════════════════
// Circuit Patterns
// ═══════════════════════════════════════════════════════════════

function createCircuitPatterns() {
  const circuitMaterial = new THREE.LineBasicMaterial({
    color: 0x00d4ff,
    transparent: true,
    opacity: 0.6
  });

  // Create geometric circuit lines on the face
  const circuits = [
    // Forehead circuits
    { points: [[-0.8, 1.2, 1.5], [-0.5, 1.3, 1.6], [0, 1.4, 1.6], [0.5, 1.3, 1.6], [0.8, 1.2, 1.5]] },
    { points: [[-0.6, 1.0, 1.6], [-0.3, 1.1, 1.65], [0.3, 1.1, 1.65], [0.6, 1.0, 1.6]] },
    
    // Cheek circuits
    { points: [[-1.2, 0, 1.3], [-1.3, -0.3, 1.2], [-1.2, -0.6, 1.1]] },
    { points: [[1.2, 0, 1.3], [1.3, -0.3, 1.2], [1.2, -0.6, 1.1]] },
    
    // Temple circuits
    { points: [[-1.5, 0.5, 0.8], [-1.6, 0.3, 0.7], [-1.5, 0, 0.6]] },
    { points: [[1.5, 0.5, 0.8], [1.6, 0.3, 0.7], [1.5, 0, 0.6]] },
  ];

  circuits.forEach(circuit => {
    const points = circuit.points.map(p => new THREE.Vector3(...p));
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const line = new THREE.Line(geometry, circuitMaterial);
    head.add(line);
  });

  // Add small glowing nodes at circuit intersections
  const nodeMaterial = new THREE.MeshBasicMaterial({
    color: 0x00ffff,
    transparent: true,
    opacity: 0.8
  });

  const nodePositions = [
    [-0.8, 1.2, 1.5], [0.8, 1.2, 1.5], [0, 1.4, 1.6],
    [-1.2, 0, 1.3], [1.2, 0, 1.3],
    [-1.5, 0.5, 0.8], [1.5, 0.5, 0.8]
  ];

  nodePositions.forEach(pos => {
    const nodeGeometry = new THREE.SphereGeometry(0.05, 8, 8);
    const node = new THREE.Mesh(nodeGeometry, nodeMaterial);
    node.position.set(...pos);
    head.add(node);
  });
}

// ═══════════════════════════════════════════════════════════════
// Eyes
// ═══════════════════════════════════════════════════════════════

function createEyes() {
  const eyePositions = [
    { x: -0.6, y: 0.3, z: 1.7 },  // Left eye
    { x: 0.6, y: 0.3, z: 1.7 }    // Right eye
  ];

  eyePositions.forEach((pos, index) => {
    // Eye socket (dark area)
    const socketGeometry = new THREE.SphereGeometry(0.35, 32, 32);
    const socketMaterial = new THREE.MeshBasicMaterial({
      color: 0x000000,
      transparent: true,
      opacity: 0.8
    });
    const socket = new THREE.Mesh(socketGeometry, socketMaterial);
    socket.position.set(pos.x, pos.y, pos.z);
    socket.scale.set(1, 0.7, 0.5);
    head.add(socket);

    // Eye glow (iris)
    const eyeGeometry = new THREE.SphereGeometry(0.25, 32, 32);
    const eyeMaterial = new THREE.MeshBasicMaterial({
      color: 0x00d4ff,
      transparent: true,
      opacity: 0.9
    });
    const eye = new THREE.Mesh(eyeGeometry, eyeMaterial);
    eye.position.set(pos.x, pos.y, pos.z + 0.1);
    eye.scale.set(1, 0.7, 0.5);
    head.add(eye);
    eyes.push(eye);

    // Eye glow effect
    const glowGeometry = new THREE.SphereGeometry(0.35, 16, 16);
    const glowMaterial = new THREE.MeshBasicMaterial({
      color: 0x00d4ff,
      transparent: true,
      opacity: 0.3,
      blending: THREE.AdditiveBlending
    });
    const glow = new THREE.Mesh(glowGeometry, glowMaterial);
    glow.position.set(pos.x, pos.y, pos.z + 0.05);
    glow.scale.set(1, 0.7, 0.5);
    head.add(glow);
    eye.userData.glow = glow;
  });
}

// ═══════════════════════════════════════════════════════════════
// Mouth/Voice Indicator
// ═══════════════════════════════════════════════════════════════

function createMouth() {
  // Mouth area - horizontal line that animates when speaking
  const mouthGeometry = new THREE.BoxGeometry(0.8, 0.05, 0.1);
  const mouthMaterial = new THREE.MeshBasicMaterial({
    color: 0x00d4ff,
    transparent: true,
    opacity: 0.7
  });

  mouth = new THREE.Mesh(mouthGeometry, mouthMaterial);
  mouth.position.set(0, -0.8, 1.8);
  head.add(mouth);

  // Add mouth glow
  const glowGeometry = new THREE.BoxGeometry(1, 0.15, 0.2);
  const glowMaterial = new THREE.MeshBasicMaterial({
    color: 0x00d4ff,
    transparent: true,
    opacity: 0.2,
    blending: THREE.AdditiveBlending
  });
  const glow = new THREE.Mesh(glowGeometry, glowMaterial);
  glow.position.set(0, -0.8, 1.75);
  head.add(glow);
  mouth.userData.glow = glow;
}

// ═══════════════════════════════════════════════════════════════
// Orbital Rings (around head)
// ═══════════════════════════════════════════════════════════════

function createRings() {
  const ringConfigs = [
    { radius: 3.5, tube: 0.02, rotation: [0, 0, Math.PI / 6], speed: 0.4, color: 0x00d4ff },
    { radius: 4, tube: 0.015, rotation: [Math.PI / 4, 0, 0], speed: -0.3, color: 0x0099cc },
    { radius: 4.5, tube: 0.01, rotation: [Math.PI / 2, Math.PI / 4, 0], speed: 0.5, color: 0x0066ff },
  ];

  ringConfigs.forEach(config => {
    const geometry = new THREE.TorusGeometry(config.radius, config.tube, 16, 100);
    const material = new THREE.MeshBasicMaterial({
      color: config.color,
      transparent: true,
      opacity: 0.5
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
  const particleCount = 2000;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(particleCount * 3);
  const colors = new Float32Array(particleCount * 3);

  const color = new THREE.Color();

  for (let i = 0; i < particleCount; i++) {
    // Random position in sphere
    const radius = 6 + Math.random() * 15;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);

    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = radius * Math.cos(phi);

    // Random colors (cyan/blue/green)
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
    opacity: 0.6,
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

  // Head subtle movement
  if (head) {
    head.rotation.y = Math.sin(time * 0.3) * 0.15;
    head.rotation.x = Math.sin(time * 0.2) * 0.05;
    head.position.y = Math.sin(time * 0.5) * 0.1;
  }

  // Eye pulsing
  eyes.forEach(eye => {
    const pulse = 0.9 + Math.sin(time * 2) * 0.1;
    eye.scale.set(pulse, pulse * 0.7, pulse * 0.5);
    if (eye.userData.glow) {
      eye.userData.glow.material.opacity = 0.2 + Math.sin(time * 2) * 0.1;
    }
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
  let mouthScale = 1;

  switch(state) {
    case 'thinking':
      // Yellow eyes, pulsing
      eyeColor.setHex(0xffaa00);
      head.material.emissive.setHex(0x332200);
      head.material.emissiveIntensity = 0.5;
      mouthScale = 1.2;
      break;
      
    case 'speaking':
      // Green eyes, mouth animates
      eyeColor.setHex(0x00ffaa);
      head.material.emissive.setHex(0x003322);
      head.material.emissiveIntensity = 0.6;
      mouthScale = 1.5 + Math.sin(Date.now() * 0.01) * 0.5;
      break;
      
    case 'active':
      // Bright cyan eyes
      eyeColor.setHex(0x00ff88);
      head.material.emissive.setHex(0x002211);
      head.material.emissiveIntensity = 0.4;
      mouthScale = 1;
      break;
      
    default: // standby
      // Cyan eyes
      eyeColor.setHex(0x00d4ff);
      head.material.emissive.setHex(0x001133);
      head.material.emissiveIntensity = 0.3;
      mouthScale = 1;
  }

  // Update eye colors
  eyes.forEach(eye => {
    eye.material.color.copy(eyeColor);
    if (eye.userData.glow) {
      eye.userData.glow.material.color.copy(eyeColor);
    }
  });

  // Update mouth for speaking
  if (mouth) {
    mouth.scale.y = mouthScale;
    if (mouth.userData.glow) {
      mouth.userData.glow.scale.y = mouthScale;
      mouth.userData.glow.material.opacity = state === 'speaking' ? 0.4 : 0.2;
    }
  }
}

// Initialize scene when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initScene);
} else {
  initScene();
}
