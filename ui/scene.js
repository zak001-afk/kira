// ═══════════════════════════════════════════════════════════════
// KIRA 3D Scene - Three.js Implementation
// ═══════════════════════════════════════════════════════════════

let scene, camera, renderer;
let core, rings = [], particles;
let clock = new THREE.Clock();

// ═══════════════════════════════════════════════════════════════
// Scene Setup
// ═══════════════════════════════════════════════════════════════

function initScene() {
  // Scene
  scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x0a0e27, 0.015);

  // Camera
  camera = new THREE.PerspectiveCamera(
    60,
    window.innerWidth / window.innerHeight,
    0.1,
    1000
  );
  camera.position.set(0, 2, 12);
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
  const ambientLight = new THREE.AmbientLight(0x00d4ff, 0.3);
  scene.add(ambientLight);

  const pointLight1 = new THREE.PointLight(0x00d4ff, 2, 50);
  pointLight1.position.set(5, 5, 5);
  scene.add(pointLight1);

  const pointLight2 = new THREE.PointLight(0x0066ff, 1.5, 50);
  pointLight2.position.set(-5, -5, 5);
  scene.add(pointLight2);

  const pointLight3 = new THREE.PointLight(0x00ffaa, 1, 50);
  pointLight3.position.set(0, 5, -5);
  scene.add(pointLight3);

  // Create objects
  createCore();
  createRings();
  createParticles();
  createGrid();

  // Handle resize
  window.addEventListener('resize', onWindowResize);

  // Start animation
  animate();
}

// ═══════════════════════════════════════════════════════════════
// Core Sphere
// ═══════════════════════════════════════════════════════════════

function createCore() {
  // Main sphere
  const geometry = new THREE.SphereGeometry(1.5, 64, 64);
  const material = new THREE.MeshPhysicalMaterial({
    color: 0x00d4ff,
    emissive: 0x00d4ff,
    emissiveIntensity: 0.5,
    metalness: 0.9,
    roughness: 0.1,
    clearcoat: 1.0,
    clearcoatRoughness: 0.1,
    transparent: true,
    opacity: 0.8
  });

  core = new THREE.Mesh(geometry, material);
  scene.add(core);

  // Inner glow
  const glowGeometry = new THREE.SphereGeometry(1.8, 32, 32);
  const glowMaterial = new THREE.MeshBasicMaterial({
    color: 0x00d4ff,
    transparent: true,
    opacity: 0.2,
    side: THREE.BackSide
  });

  const glow = new THREE.Mesh(glowGeometry, glowMaterial);
  core.add(glow);

  // Wireframe overlay
  const wireGeometry = new THREE.SphereGeometry(1.55, 32, 32);
  const wireMaterial = new THREE.MeshBasicMaterial({
    color: 0x00ffff,
    wireframe: true,
    transparent: true,
    opacity: 0.3
  });

  const wireframe = new THREE.Mesh(wireGeometry, wireMaterial);
  core.add(wireframe);
}

// ═══════════════════════════════════════════════════════════════
// Orbital Rings
// ═══════════════════════════════════════════════════════════════

function createRings() {
  const ringConfigs = [
    { radius: 3, tube: 0.02, rotation: [0, 0, 0], speed: 0.5, color: 0x00d4ff },
    { radius: 3.5, tube: 0.015, rotation: [Math.PI / 4, 0, 0], speed: -0.3, color: 0x0099cc },
    { radius: 4, tube: 0.01, rotation: [Math.PI / 2, Math.PI / 4, 0], speed: 0.4, color: 0x0066ff },
    { radius: 4.5, tube: 0.008, rotation: [Math.PI / 3, Math.PI / 2, 0], speed: -0.6, color: 0x00ffaa }
  ];

  ringConfigs.forEach(config => {
    const geometry = new THREE.TorusGeometry(config.radius, config.tube, 16, 100);
    const material = new THREE.MeshBasicMaterial({
      color: config.color,
      transparent: true,
      opacity: 0.6
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
  const sizes = new Float32Array(particleCount);

  const color = new THREE.Color();

  for (let i = 0; i < particleCount; i++) {
    // Random position in sphere
    const radius = 5 + Math.random() * 15;
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

    // Random sizes
    sizes[i] = Math.random() * 2 + 0.5;
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

  const material = new THREE.PointsMaterial({
    size: 0.1,
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
  gridHelper.position.y = -5;
  gridHelper.material.opacity = 0.2;
  gridHelper.material.transparent = true;
  scene.add(gridHelper);
}

// ═══════════════════════════════════════════════════════════════
// Animation Loop
// ═══════════════════════════════════════════════════════════════

function animate() {
  requestAnimationFrame(animate);

  const time = clock.getElapsedTime();

  // Rotate core
  if (core) {
    core.rotation.y = time * 0.2;
    core.rotation.x = Math.sin(time * 0.3) * 0.1;
    
    // Pulse effect
    const scale = 1 + Math.sin(time * 2) * 0.05;
    core.scale.set(scale, scale, scale);
  }

  // Rotate rings
  rings.forEach((ring, index) => {
    ring.rotation.z += ring.userData.speed * 0.01;
    ring.rotation.x += ring.userData.speed * 0.005;
  });

  // Rotate particles
  if (particles) {
    particles.rotation.y = time * 0.05;
    particles.rotation.x = Math.sin(time * 0.1) * 0.1;
  }

  // Camera gentle movement
  camera.position.x = Math.sin(time * 0.1) * 0.5;
  camera.position.y = 2 + Math.sin(time * 0.15) * 0.3;
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
  if (!core) return;

  switch(state) {
    case 'thinking':
      core.material.emissiveIntensity = 1.0;
      core.material.emissive.setHex(0xffaa00);
      break;
    case 'speaking':
      core.material.emissiveIntensity = 1.2;
      core.material.emissive.setHex(0x00ffaa);
      break;
    case 'active':
      core.material.emissiveIntensity = 0.8;
      core.material.emissive.setHex(0x00ff88);
      break;
    default:
      core.material.emissiveIntensity = 0.5;
      core.material.emissive.setHex(0x00d4ff);
  }
}

// Initialize scene when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initScene);
} else {
  initScene();
}
