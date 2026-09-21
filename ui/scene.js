// ═══════════════════════════════════════════════════════════════
// KIRA Human Face with Matrix Theme - Three.js Implementation
// ═══════════════════════════════════════════════════════════════

let scene, camera, renderer;
let head, eyes = [], lips, nose, eyebrows = [], digitalRain, auraParticles;
let clock = new THREE.Clock();
let currentActivity = 'standby';

// ═══════════════════════════════════════════════════════════════
// Scene Setup
// ═══════════════════════════════════════════════════════════════

function initScene() {
  // Scene
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x000000);
  scene.fog = new THREE.FogExp2(0x000000, 0.012);

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
    alpha: false
  });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;

  // Lighting - Matrix green with human face lighting
  const ambientLight = new THREE.AmbientLight(0x00ff41, 0.4);
  scene.add(ambientLight);

  const keyLight = new THREE.DirectionalLight(0xffffff, 0.8);
  keyLight.position.set(5, 5, 5);
  scene.add(keyLight);

  const fillLight = new THREE.DirectionalLight(0x00ff41, 0.5);
  fillLight.position.set(-5, 0, 5);
  scene.add(fillLight);

  const rimLight = new THREE.DirectionalLight(0x00aa00, 0.6);
  rimLight.position.set(0, 5, -5);
  scene.add(rimLight);

  const bottomLight = new THREE.PointLight(0x00ff41, 0.4, 20);
  bottomLight.position.set(0, -3, 3);
  scene.add(bottomLight);

  // Create Matrix effects
  createDigitalRain();
  
  // Create human face
  createHead();
  createNose();
  createEyes();
  createEyebrows();
  createLips();
  createDigitalAura();
  createGrid();

  // Handle resize
  window.addEventListener('resize', onWindowResize);

  // Start animation
  animate();
}

// ═══════════════════════════════════════════════════════════════
// Digital Rain (Matrix Effect)
// ═══════════════════════════════════════════════════════════════

function createDigitalRain() {
  const rainCount = 2500;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(rainCount * 3);
  const velocities = new Float32Array(rainCount);

  for (let i = 0; i < rainCount; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 60;
    positions[i * 3 + 1] = Math.random() * 40 - 10;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 60 - 15;
    velocities[i] = 0.08 + Math.random() * 0.15;
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  const material = new THREE.PointsMaterial({
    color: 0x00ff41,
    size: 0.12,
    transparent: true,
    opacity: 0.5,
    blending: THREE.AdditiveBlending
  });

  digitalRain = new THREE.Points(geometry, material);
  digitalRain.userData.velocities = velocities;
  scene.add(digitalRain);
}

// ═══════════════════════════════════════════════════════════════
// Human Head with Matrix Tint
// ═══════════════════════════════════════════════════════════════

function createHead() {
  const headGeometry = new THREE.SphereGeometry(2, 64, 64);
  const positions = headGeometry.attributes.position;
  
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i);
    const y = positions.getY(i);
    const z = positions.getZ(i);
    
    // Human-like head shape
    positions.setY(i, y * 1.25);
    positions.setX(i, x * 0.92);
    
    // Jaw/chin
    if (y < -0.3) {
      const factor = 1 - Math.abs(y + 0.3) * 0.4;
      positions.setX(i, x * factor);
      positions.setZ(i, z * Math.max(0.7, factor));
    }
    
    // Flatten back
    if (z < -0.5) {
      positions.setZ(i, z * 0.85);
    }
    
    // Forehead
    if (y > 1.0 && z > 0) {
      positions.setZ(i, z * 1.1);
    }
  }
  
  headGeometry.computeVertexNormals();

  // Matrix-tinted skin material
  const headMaterial = new THREE.MeshPhysicalMaterial({
    color: 0x88aa88,  // Green-tinted skin
    emissive: 0x003300,
    emissiveIntensity: 0.3,
    metalness: 0.2,
    roughness: 0.5,
    clearcoat: 0.4,
    clearcoatRoughness: 0.3,
    sheen: 0.6,
    sheenRoughness: 0.7,
    sheenColor: new THREE.Color(0x00ff41)
  });

  head = new THREE.Mesh(headGeometry, headMaterial);
  scene.add(head);

  // Subtle digital glow
  const glowGeometry = new THREE.SphereGeometry(2.05, 32, 32);
  const glowMaterial = new THREE.MeshBasicMaterial({
    color: 0x00ff41,
    transparent: true,
    opacity: 0.08,
    side: THREE.BackSide
  });
  const glow = new THREE.Mesh(glowGeometry, glowMaterial);
  head.add(glow);
}

// ═══════════════════════════════════════════════════════════════
// Nose
// ═══════════════════════════════════════════════════════════════

function createNose() {
  const bridgeGeometry = new THREE.CylinderGeometry(0.12, 0.18, 0.8, 16);
  const noseMaterial = new THREE.MeshPhysicalMaterial({
    color: 0x88aa88,
    emissive: 0x003300,
    emissiveIntensity: 0.3,
    metalness: 0.2,
    roughness: 0.5
  });
  
  nose = new THREE.Mesh(bridgeGeometry, noseMaterial);
  nose.position.set(0, -0.1, 1.9);
  nose.rotation.x = Math.PI / 2;
  head.add(nose);

  const tipGeometry = new THREE.SphereGeometry(0.2, 16, 16);
  const tip = new THREE.Mesh(tipGeometry, noseMaterial);
  tip.position.set(0, -0.5, 2.0);
  tip.scale.set(1, 0.8, 1.2);
  head.add(tip);
}

// ═══════════════════════════════════════════════════════════════
// Eyes with Matrix Glow
// ═══════════════════════════════════════════════════════════════

function createEyes() {
  const eyePositions = [
    { x: -0.55, y: 0.35, z: 1.75 },
    { x: 0.55, y: 0.35, z: 1.75 }
  ];

  eyePositions.forEach((pos) => {
    // Eye socket
    const socketGeometry = new THREE.SphereGeometry(0.38, 32, 32);
    const socketMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x667766,
      metalness: 0.2,
      roughness: 0.6
    });
    const socket = new THREE.Mesh(socketGeometry, socketMaterial);
    socket.position.set(pos.x, pos.y, pos.z - 0.1);
    socket.scale.set(1, 0.75, 0.6);
    head.add(socket);

    // Eyeball
    const eyeballGeometry = new THREE.SphereGeometry(0.28, 32, 32);
    const eyeballMaterial = new THREE.MeshPhysicalMaterial({
      color: 0xeeffee,
      metalness: 0,
      roughness: 0.3,
      clearcoat: 1,
      clearcoatRoughness: 0.1
    });
    const eyeball = new THREE.Mesh(eyeballGeometry, eyeballMaterial);
    eyeball.position.set(pos.x, pos.y, pos.z);
    eyeball.scale.set(1, 0.75, 0.6);
    head.add(eyeball);

    // Iris (Matrix green)
    const irisGeometry = new THREE.SphereGeometry(0.16, 32, 32);
    const irisMaterial = new THREE.MeshBasicMaterial({
      color: 0x00ff41,
      transparent: true,
      opacity: 0.95
    });
    const iris = new THREE.Mesh(irisGeometry, irisMaterial);
    iris.position.set(pos.x, pos.y, pos.z + 0.15);
    iris.scale.set(1, 0.75, 0.4);
    head.add(iris);
    eyes.push(iris);

    // Pupil
    const pupilGeometry = new THREE.SphereGeometry(0.08, 16, 16);
    const pupilMaterial = new THREE.MeshBasicMaterial({
      color: 0x000000
    });
    const pupil = new THREE.Mesh(pupilGeometry, pupilMaterial);
    pupil.position.set(pos.x, pos.y, pos.z + 0.18);
    pupil.scale.set(1, 0.75, 0.4);
    head.add(pupil);

    // Matrix glow
    const glowGeometry = new THREE.SphereGeometry(0.22, 16, 16);
    const glowMaterial = new THREE.MeshBasicMaterial({
      color: 0x00ff41,
      transparent: true,
      opacity: 0.35,
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
    { x: -0.55, y: 0.75, z: 1.7, rotation: -0.2 },
    { x: 0.55, y: 0.75, z: 1.7, rotation: 0.2 }
  ];

  eyebrowPositions.forEach((pos) => {
    const eyebrowGeometry = new THREE.BoxGeometry(0.5, 0.08, 0.1);
    const eyebrowMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x445544,
      metalness: 0.3,
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
  const upperLipGeometry = new THREE.TorusGeometry(0.3, 0.08, 16, 32, Math.PI);
  const lipMaterial = new THREE.MeshPhysicalMaterial({
    color: 0x778877,
    emissive: 0x002200,
    emissiveIntensity: 0.2,
    metalness: 0.2,
    roughness: 0.4,
    clearcoat: 0.6,
    clearcoatRoughness: 0.3
  });
  
  const upperLip = new THREE.Mesh(upperLipGeometry, lipMaterial);
  upperLip.position.set(0, -0.85, 1.85);
  upperLip.rotation.x = Math.PI;
  upperLip.scale.set(1, 0.5, 1);
  head.add(upperLip);

  const lowerLipGeometry = new THREE.TorusGeometry(0.32, 0.1, 16, 32, Math.PI);
  const lowerLip = new THREE.Mesh(lowerLipGeometry, lipMaterial);
  lowerLip.position.set(0, -0.95, 1.85);
  lowerLip.scale.set(1, 0.6, 1);
  head.add(lowerLip);

  lips = { upper: upperLip, lower: lowerLip };
}

// ═══════════════════════════════════════════════════════════════
// Digital Aura (Particles around face)
// ═══════════════════════════════════════════════════════════════

function createDigitalAura() {
  const particleCount = 800;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(particleCount * 3);
  const colors = new Float32Array(particleCount * 3);

  const color = new THREE.Color();

  for (let i = 0; i < particleCount; i++) {
    // Particles around the head
    const radius = 2.5 + Math.random() * 1.5;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);

    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = radius * Math.cos(phi);

    // Matrix green variations
    const hue = 0.33 + (Math.random() - 0.5) * 0.03;
    color.setHSL(hue, 1.0, 0.5 + Math.random() * 0.2);
    
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  const material = new THREE.PointsMaterial({
    size: 0.06,
    vertexColors: true,
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending
  });

  auraParticles = new THREE.Points(geometry, material);
  scene.add(auraParticles);
}

// ═══════════════════════════════════════════════════════════════
// Grid Floor
// ═══════════════════════════════════════════════════════════════

function createGrid() {
  const gridHelper = new THREE.GridHelper(80, 80, 0x00ff41, 0x004400);
  gridHelper.position.y = -4;
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

  // Animate digital rain
  if (digitalRain) {
    const positions = digitalRain.geometry.attributes.position.array;
    const velocities = digitalRain.userData.velocities;
    
    for (let i = 0; i < positions.length / 3; i++) {
      positions[i * 3 + 1] -= velocities[i];
      
      if (positions[i * 3 + 1] < -10) {
        positions[i * 3 + 1] = 30;
        positions[i * 3] = (Math.random() - 0.5) * 60;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 60 - 15;
      }
    }
    
    digitalRain.geometry.attributes.position.needsUpdate = true;
  }

  // Head natural movement
  if (head) {
    head.rotation.y = Math.sin(time * 0.3) * 0.12;
    head.rotation.x = Math.sin(time * 0.2) * 0.04;
    head.position.y = Math.sin(time * 0.5) * 0.08;
  }

  // Eye pulsing
  eyes.forEach((eye, index) => {
    const pulse = 1 + Math.sin(time * 2 + index) * 0.08;
    eye.scale.set(pulse, pulse * 0.75, pulse * 0.4);
    
    if (eye.userData.glow) {
      eye.userData.glow.material.opacity = 0.25 + Math.sin(time * 2) * 0.1;
    }
  });

  // Eyebrow movement
  eyebrows.forEach((eyebrow, index) => {
    const lift = Math.sin(time * 0.5 + index) * 0.02;
    eyebrow.position.y = 0.75 + lift;
  });

  // Aura particles rotation
  if (auraParticles) {
    auraParticles.rotation.y = time * 0.05;
    auraParticles.rotation.x = Math.sin(time * 0.1) * 0.05;
  }

  // Camera gentle movement
  camera.position.x = Math.sin(time * 0.1) * 0.35;
  camera.position.y = 1 + Math.sin(time * 0.15) * 0.22;
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
  currentActivity = state;
  
  if (!head || !eyes.length) return;

  const eyeColor = new THREE.Color();
  let lipSeparation = 0;

  switch(state) {
    case 'thinking':
      eyeColor.setHex(0x88ff88);
      head.material.emissive.setHex(0x004400);
      head.material.emissiveIntensity = 0.5;
      eyebrows.forEach(eb => eb.position.y = 0.78);
      break;
      
    case 'speaking':
      eyeColor.setHex(0x00ff88);
      head.material.emissive.setHex(0x005500);
      head.material.emissiveIntensity = 0.6;
      lipSeparation = 0.05 + Math.sin(Date.now() * 0.015) * 0.03;
      eyebrows.forEach(eb => eb.position.y = 0.75);
      break;
      
    case 'active':
      eyeColor.setHex(0x00ff41);
      head.material.emissive.setHex(0x003300);
      head.material.emissiveIntensity = 0.4;
      eyebrows.forEach(eb => eb.position.y = 0.76);
      break;
      
    default: // standby
      eyeColor.setHex(0x00aa00);
      head.material.emissive.setHex(0x003300);
      head.material.emissiveIntensity = 0.3;
      eyebrows.forEach(eb => eb.position.y = 0.75);
  }

  eyes.forEach(eye => {
    eye.material.color.copy(eyeColor);
    if (eye.userData.glow) {
      eye.userData.glow.material.color.copy(eyeColor);
    }
  });

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
