// ═══════════════════════════════════════════════════════════════
// KIRA Realistic Human Face with Matrix Skin - Three.js
// ═══════════════════════════════════════════════════════════════

let scene, camera, renderer;
let head, eyes = [], lips, nose, eyebrows = [], digitalRain, skinCircuits;
let clock = new THREE.Clock();
let currentActivity = 'standby';

// ═══════════════════════════════════════════════════════════════
// Scene Setup
// ═══════════════════════════════════════════════════════════════

function initScene() {
  // Scene
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x000000);
  scene.fog = new THREE.FogExp2(0x000000, 0.01);

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
  renderer.toneMappingExposure = 1.2;

  // Lighting - Professional portrait lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
  scene.add(ambientLight);

  const keyLight = new THREE.DirectionalLight(0xffffff, 1.2);
  keyLight.position.set(5, 5, 5);
  scene.add(keyLight);

  const fillLight = new THREE.DirectionalLight(0x88aaff, 0.6);
  fillLight.position.set(-5, 2, 5);
  scene.add(fillLight);

  const rimLight = new THREE.DirectionalLight(0x00ff41, 0.8);
  rimLight.position.set(0, 3, -5);
  scene.add(rimLight);

  const bottomLight = new THREE.PointLight(0x00ff41, 0.3, 20);
  bottomLight.position.set(0, -3, 3);
  scene.add(bottomLight);

  // Create elements
  createDigitalRain();
  createHead();
  createSkinCircuits();
  createNose();
  createEyes();
  createEyebrows();
  createLips();
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
  const rainCount = 2000;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(rainCount * 3);
  const velocities = new Float32Array(rainCount);

  for (let i = 0; i < rainCount; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 60;
    positions[i * 3 + 1] = Math.random() * 40 - 10;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 60 - 15;
    velocities[i] = 0.06 + Math.random() * 0.12;
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  const material = new THREE.PointsMaterial({
    color: 0x00ff41,
    size: 0.1,
    transparent: true,
    opacity: 0.4,
    blending: THREE.AdditiveBlending
  });

  digitalRain = new THREE.Points(geometry, material);
  digitalRain.userData.velocities = velocities;
  scene.add(digitalRain);
}

// ═══════════════════════════════════════════════════════════════
// Realistic Human Head
// ═══════════════════════════════════════════════════════════════

function createHead() {
  const headGeometry = new THREE.SphereGeometry(2, 64, 64);
  const positions = headGeometry.attributes.position;
  
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i);
    const y = positions.getY(i);
    const z = positions.getZ(i);
    
    // Realistic human head proportions
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
    
    // Cheekbones
    if (y > -0.3 && y < 0.3 && Math.abs(x) > 1.2 && z > 0.5) {
      positions.setX(i, x * 1.05);
    }
  }
  
  headGeometry.computeVertexNormals();

  // Realistic skin material
  const headMaterial = new THREE.MeshPhysicalMaterial({
    color: 0xffdbac,  // Realistic skin tone
    emissive: 0x000000,
    emissiveIntensity: 0,
    metalness: 0.0,
    roughness: 0.7,
    clearcoat: 0.2,
    clearcoatRoughness: 0.4,
    sheen: 1.0,
    sheenRoughness: 0.5,
    sheenColor: new THREE.Color(0xffaa88),
    transmission: 0.1,
    thickness: 0.5
  });

  head = new THREE.Mesh(headGeometry, headMaterial);
  scene.add(head);
}

// ═══════════════════════════════════════════════════════════════
// Matrix Skin Circuits
// ═══════════════════════════════════════════════════════════════

function createSkinCircuits() {
  skinCircuits = new THREE.Group();
  
  const circuitMaterial = new THREE.LineBasicMaterial({
    color: 0x00ff41,
    transparent: true,
    opacity: 0.7,
    blending: THREE.AdditiveBlending
  });

  // Circuit patterns on face
  const circuits = [
    // Forehead circuits
    { points: [[-0.8, 1.3, 1.5], [-0.5, 1.4, 1.6], [0, 1.5, 1.6], [0.5, 1.4, 1.6], [0.8, 1.3, 1.5]] },
    { points: [[-0.6, 1.1, 1.6], [-0.3, 1.2, 1.65], [0.3, 1.2, 1.65], [0.6, 1.1, 1.6]] },
    { points: [[-0.4, 1.0, 1.65], [0, 1.1, 1.7], [0.4, 1.0, 1.65]] },
    
    // Temple circuits
    { points: [[-1.5, 0.6, 0.9], [-1.6, 0.3, 0.8], [-1.5, 0, 0.7], [-1.4, -0.3, 0.6]] },
    { points: [[1.5, 0.6, 0.9], [1.6, 0.3, 0.8], [1.5, 0, 0.7], [1.4, -0.3, 0.6]] },
    
    // Cheek circuits
    { points: [[-1.2, -0.1, 1.4], [-1.3, -0.4, 1.3], [-1.2, -0.7, 1.2]] },
    { points: [[1.2, -0.1, 1.4], [1.3, -0.4, 1.3], [1.2, -0.7, 1.2]] },
    
    // Jaw line circuits
    { points: [[-0.8, -1.2, 1.3], [-0.4, -1.4, 1.4], [0, -1.5, 1.5], [0.4, -1.4, 1.4], [0.8, -1.2, 1.3]] },
  ];

  circuits.forEach(circuit => {
    const points = circuit.points.map(p => new THREE.Vector3(...p));
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const line = new THREE.Line(geometry, circuitMaterial);
    skinCircuits.add(line);
  });

  // Glowing nodes at circuit intersections
  const nodeMaterial = new THREE.MeshBasicMaterial({
    color: 0x00ff88,
    transparent: true,
    opacity: 0.9
  });

  const nodePositions = [
    [-0.8, 1.3, 1.5], [0.8, 1.3, 1.5], [0, 1.5, 1.6],
    [-1.5, 0.6, 0.9], [1.5, 0.6, 0.9],
    [-1.2, -0.1, 1.4], [1.2, -0.1, 1.4],
    [-0.8, -1.2, 1.3], [0.8, -1.2, 1.3], [0, -1.5, 1.5]
  ];

  nodePositions.forEach(pos => {
    const nodeGeometry = new THREE.SphereGeometry(0.04, 8, 8);
    const node = new THREE.Mesh(nodeGeometry, nodeMaterial);
    node.position.set(...pos);
    skinCircuits.add(node);
  });

  scene.add(skinCircuits);
}

// ═══════════════════════════════════════════════════════════════
// Nose
// ═══════════════════════════════════════════════════════════════

function createNose() {
  const bridgeGeometry = new THREE.CylinderGeometry(0.12, 0.18, 0.8, 16);
  const noseMaterial = new THREE.MeshPhysicalMaterial({
    color: 0xffdbac,
    metalness: 0.0,
    roughness: 0.7,
    sheen: 1.0,
    sheenRoughness: 0.5,
    sheenColor: new THREE.Color(0xffaa88)
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
// Eyes
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
      color: 0xffccaa,
      metalness: 0.0,
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
      roughness: 0.2,
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
    { x: -0.55, y: 0.75, z: 1.7, rotation: -0.2 },
    { x: 0.55, y: 0.75, z: 1.7, rotation: 0.2 }
  ];

  eyebrowPositions.forEach((pos) => {
    const eyebrowGeometry = new THREE.BoxGeometry(0.5, 0.08, 0.1);
    const eyebrowMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x3a2820,  // Dark brown
      metalness: 0.1,
      roughness: 0.6
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
    color: 0xcc6666,  // Natural lip color
    emissive: 0x000000,
    emissiveIntensity: 0,
    metalness: 0.0,
    roughness: 0.3,
    clearcoat: 0.8,
    clearcoatRoughness: 0.2
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
// Grid Floor
// ═══════════════════════════════════════════════════════════════

function createGrid() {
  const gridHelper = new THREE.GridHelper(80, 80, 0x00ff41, 0x003300);
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

  // Skin circuits follow head
  if (skinCircuits) {
    skinCircuits.rotation.copy(head.rotation);
    skinCircuits.position.copy(head.position);
    
    // Pulse circuit opacity
    skinCircuits.children.forEach((child, index) => {
      if (child.material) {
        child.material.opacity = 0.5 + Math.sin(time * 2 + index * 0.5) * 0.2;
      }
    });
  }

  // Eye pulsing
  eyes.forEach((eye, index) => {
    const pulse = 1 + Math.sin(time * 2 + index) * 0.08;
    eye.scale.set(pulse, pulse * 0.75, pulse * 0.4);
    
    if (eye.userData.glow) {
      eye.userData.glow.material.opacity = 0.2 + Math.sin(time * 2) * 0.1;
    }
  });

  // Eyebrow movement
  eyebrows.forEach((eyebrow, index) => {
    const lift = Math.sin(time * 0.5 + index) * 0.02;
    eyebrow.position.y = 0.75 + lift;
  });

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
  currentActivity = state;
  
  if (!head || !eyes.length) return;

  const eyeColor = new THREE.Color();
  let lipSeparation = 0;
  let circuitBrightness = 1;

  switch(state) {
    case 'thinking':
      eyeColor.setHex(0x88ff88);
      circuitBrightness = 1.5;
      eyebrows.forEach(eb => eb.position.y = 0.78);
      break;
      
    case 'speaking':
      eyeColor.setHex(0x00ff88);
      circuitBrightness = 1.3;
      lipSeparation = 0.05 + Math.sin(Date.now() * 0.015) * 0.03;
      eyebrows.forEach(eb => eb.position.y = 0.75);
      break;
      
    case 'active':
      eyeColor.setHex(0x00ff41);
      circuitBrightness = 1.2;
      eyebrows.forEach(eb => eb.position.y = 0.76);
      break;
      
    default: // standby
      eyeColor.setHex(0x00aa00);
      circuitBrightness = 0.8;
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

  // Adjust circuit brightness
  if (skinCircuits) {
    skinCircuits.children.forEach(child => {
      if (child.material) {
        const baseOpacity = child.material.opacity;
        child.material.opacity = Math.min(1, baseOpacity * circuitBrightness);
      }
    });
  }
}

// Initialize scene when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initScene);
} else {
  initScene();
}
