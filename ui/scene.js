// ═══════════════════════════════════════════════════════════════
// KIRA Matrix-Style Digital Face - Three.js Implementation
// ═══════════════════════════════════════════════════════════════

let scene, camera, renderer;
let faceParticles, digitalRain, eyes = [], faceMesh;
let clock = new THREE.Clock();
let currentActivity = 'standby';

// ═══════════════════════════════════════════════════════════════
// Scene Setup
// ═══════════════════════════════════════════════════════════════

function initScene() {
  // Scene
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x000000);
  scene.fog = new THREE.FogExp2(0x000000, 0.015);

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

  // Lighting - Matrix green theme
  const ambientLight = new THREE.AmbientLight(0x00ff41, 0.3);
  scene.add(ambientLight);

  const keyLight = new THREE.DirectionalLight(0x00ff41, 0.8);
  keyLight.position.set(5, 5, 5);
  scene.add(keyLight);

  const rimLight = new THREE.DirectionalLight(0x00aa00, 0.5);
  rimLight.position.set(-5, 0, -5);
  scene.add(rimLight);

  // Create Matrix effects
  createDigitalRain();
  createFaceParticles();
  createEyes();
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
  const rainCount = 3000;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(rainCount * 3);
  const velocities = new Float32Array(rainCount);

  for (let i = 0; i < rainCount; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 60;
    positions[i * 3 + 1] = Math.random() * 40 - 10;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 60 - 10;
    velocities[i] = 0.1 + Math.random() * 0.2;
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  const material = new THREE.PointsMaterial({
    color: 0x00ff41,
    size: 0.15,
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending
  });

  digitalRain = new THREE.Points(geometry, material);
  digitalRain.userData.velocities = velocities;
  scene.add(digitalRain);
}

// ═══════════════════════════════════════════════════════════════
// Face Made of Particles
// ═══════════════════════════════════════════════════════════════

function createFaceParticles() {
  const particleCount = 8000;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(particleCount * 3);
  const colors = new Float32Array(particleCount * 3);
  const sizes = new Float32Array(particleCount);
  const originalPositions = new Float32Array(particleCount * 3);

  const color = new THREE.Color();

  for (let i = 0; i < particleCount; i++) {
    // Create face shape using parametric equations
    const u = Math.random() * Math.PI * 2;
    const v = Math.random() * Math.PI;
    
    // Head shape (ellipsoid)
    let x = 1.8 * Math.sin(v) * Math.cos(u);
    let y = 2.2 * Math.cos(v) * 1.1;
    let z = 1.7 * Math.sin(v) * Math.sin(u);
    
    // Add facial features through density variations
    const faceX = x / 1.8;
    const faceY = y / 2.2;
    const faceZ = z / 1.7;
    
    // Eye sockets (denser particles)
    const leftEyeDist = Math.sqrt(Math.pow(faceX + 0.3, 2) + Math.pow(faceY - 0.15, 2));
    const rightEyeDist = Math.sqrt(Math.pow(faceX - 0.3, 2) + Math.pow(faceY - 0.15, 2));
    
    // Nose ridge
    const noseDist = Math.sqrt(Math.pow(faceX, 2) + Math.pow(faceY + 0.05, 2));
    
    // Mouth area
    const mouthDist = Math.sqrt(Math.pow(faceX, 2) + Math.pow(faceY + 0.4, 2));
    
    // Only keep particles that form the face surface
    if (z > 0 || leftEyeDist < 0.15 || rightEyeDist < 0.15 || noseDist < 0.1 || mouthDist < 0.15) {
      positions[i * 3] = x;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = z;
    } else {
      // Push non-face particles outward
      positions[i * 3] = x * 1.5;
      positions[i * 3 + 1] = y * 1.5;
      positions[i * 3 + 2] = z * 1.5;
    }

    originalPositions[i * 3] = positions[i * 3];
    originalPositions[i * 3 + 1] = positions[i * 3 + 1];
    originalPositions[i * 3 + 2] = positions[i * 3 + 2];

    // Matrix green colors with variation
    const hue = 0.33 + (Math.random() - 0.5) * 0.05;
    const saturation = 0.8 + Math.random() * 0.2;
    const lightness = 0.4 + Math.random() * 0.3;
    color.setHSL(hue, saturation, lightness);
    
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;

    sizes[i] = 0.03 + Math.random() * 0.04;
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

  const material = new THREE.PointsMaterial({
    size: 0.05,
    vertexColors: true,
    transparent: true,
    opacity: 0.8,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true
  });

  faceParticles = new THREE.Points(geometry, material);
  faceParticles.userData.originalPositions = originalPositions;
  scene.add(faceParticles);
}

// ═══════════════════════════════════════════════════════════════
// Glowing Eyes
// ═══════════════════════════════════════════════════════════════

function createEyes() {
  const eyePositions = [
    { x: -0.55, y: 0.35, z: 1.8 },
    { x: 0.55, y: 0.35, z: 1.8 }
  ];

  eyePositions.forEach((pos) => {
    // Eye core
    const eyeGeometry = new THREE.SphereGeometry(0.18, 32, 32);
    const eyeMaterial = new THREE.MeshBasicMaterial({
      color: 0x00ff41,
      transparent: true,
      opacity: 0.95
    });
    const eye = new THREE.Mesh(eyeGeometry, eyeMaterial);
    eye.position.set(pos.x, pos.y, pos.z);
    eye.scale.set(1, 0.7, 0.6);
    scene.add(eye);
    eyes.push(eye);

    // Eye glow
    const glowGeometry = new THREE.SphereGeometry(0.3, 16, 16);
    const glowMaterial = new THREE.MeshBasicMaterial({
      color: 0x00ff41,
      transparent: true,
      opacity: 0.3,
      blending: THREE.AdditiveBlending
    });
    const glow = new THREE.Mesh(glowGeometry, glowMaterial);
    glow.position.set(pos.x, pos.y, pos.z);
    glow.scale.set(1, 0.7, 0.6);
    scene.add(glow);
    eye.userData.glow = glow;

    // Pupil
    const pupilGeometry = new THREE.SphereGeometry(0.08, 16, 16);
    const pupilMaterial = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.9
    });
    const pupil = new THREE.Mesh(pupilGeometry, pupilMaterial);
    pupil.position.set(pos.x, pos.y, pos.z + 0.1);
    pupil.scale.set(1, 0.7, 0.5);
    scene.add(pupil);
    eye.userData.pupil = pupil;
  });
}

// ═══════════════════════════════════════════════════════════════
// Grid Floor (Matrix Style)
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
      
      // Reset when particle falls below
      if (positions[i * 3 + 1] < -10) {
        positions[i * 3 + 1] = 30;
        positions[i * 3] = (Math.random() - 0.5) * 60;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 60 - 10;
      }
    }
    
    digitalRain.geometry.attributes.position.needsUpdate = true;
  }

  // Animate face particles (glitch effect)
  if (faceParticles) {
    const positions = faceParticles.geometry.attributes.position.array;
    const originalPositions = faceParticles.userData.originalPositions;
    
    for (let i = 0; i < positions.length / 3; i++) {
      // Base position with subtle floating
      const floatX = Math.sin(time * 0.5 + i * 0.01) * 0.02;
      const floatY = Math.cos(time * 0.3 + i * 0.01) * 0.02;
      
      // Glitch effect (occasional displacement)
      let glitchX = 0, glitchY = 0, glitchZ = 0;
      if (Math.random() < 0.001) {
        glitchX = (Math.random() - 0.5) * 0.3;
        glitchY = (Math.random() - 0.5) * 0.3;
        glitchZ = (Math.random() - 0.5) * 0.3;
      }
      
      positions[i * 3] = originalPositions[i * 3] + floatX + glitchX;
      positions[i * 3 + 1] = originalPositions[i * 3 + 1] + floatY + glitchY;
      positions[i * 3 + 2] = originalPositions[i * 3 + 2] + glitchZ;
    }
    
    faceParticles.geometry.attributes.position.needsUpdate = true;
    
    // Rotate face slightly
    faceParticles.rotation.y = Math.sin(time * 0.2) * 0.15;
    faceParticles.rotation.x = Math.sin(time * 0.15) * 0.05;
  }

  // Animate eyes
  eyes.forEach((eye, index) => {
    // Pulsing
    const pulse = 1 + Math.sin(time * 2 + index) * 0.1;
    eye.scale.set(pulse, pulse * 0.7, pulse * 0.6);
    
    // Track slightly
    const trackX = Math.sin(time * 0.4) * 0.02;
    const trackY = Math.sin(time * 0.3) * 0.01;
    
    if (eye.userData.glow) {
      eye.userData.glow.material.opacity = 0.2 + Math.sin(time * 2) * 0.1;
    }
    
    if (eye.userData.pupil) {
      eye.userData.pupil.position.x = eye.position.x + trackX;
      eye.userData.pupil.position.y = eye.position.y + trackY;
    }
  });

  // Camera gentle movement
  camera.position.x = Math.sin(time * 0.1) * 0.4;
  camera.position.y = 1 + Math.sin(time * 0.15) * 0.25;
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
  
  if (!eyes.length) return;

  const eyeColor = new THREE.Color();
  let glitchIntensity = 0;

  switch(state) {
    case 'thinking':
      // Brighter green, more glitching
      eyeColor.setHex(0x88ff88);
      glitchIntensity = 0.005;
      break;
      
    case 'speaking':
      // Intense green, pulsing
      eyeColor.setHex(0x00ff88);
      glitchIntensity = 0.003;
      break;
      
    case 'active':
      // Standard Matrix green
      eyeColor.setHex(0x00ff41);
      glitchIntensity = 0.002;
      break;
      
    default: // standby
      // Dim Matrix green
      eyeColor.setHex(0x00aa00);
      glitchIntensity = 0.001;
  }

  // Update eye colors
  eyes.forEach(eye => {
    eye.material.color.copy(eyeColor);
    if (eye.userData.glow) {
      eye.userData.glow.material.color.copy(eyeColor);
    }
  });

  // Adjust glitch intensity
  if (faceParticles) {
    faceParticles.userData.glitchIntensity = glitchIntensity;
  }
}

// Initialize scene when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initScene);
} else {
  initScene();
}
