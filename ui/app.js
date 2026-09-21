import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

/* =========================================================
   CONFIG
   ========================================================= */

const RED = 0xff2020;
const RED_BRIGHT = 0xff4545;
const RED_DARK = 0x650808;
const RED_DEEP = 0x260303;

/* =========================================================
   SCENE
   ========================================================= */

const container = document.getElementById("scene-container");
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x010101);

/* =========================================================
   CAMERA
   ========================================================= */

const camera = new THREE.PerspectiveCamera(
  45,
  window.innerWidth / window.innerHeight,
  0.1,
  1000
);
camera.position.set(0, 0, 15);

/* =========================================================
   RENDERER
   ========================================================= */

const renderer = new THREE.WebGLRenderer({
  antialias: true,
  alpha: true,
});
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
container.appendChild(renderer.domElement);

/* =========================================================
   LIGHTING
   ========================================================= */

const ambient = new THREE.AmbientLight(0x120000, 2);
scene.add(ambient);

const redLight = new THREE.PointLight(RED, 18, 12);
redLight.position.set(0, 0, 2);
scene.add(redLight);

const composer = new EffectComposer(renderer);
const renderPass = new RenderPass(scene, camera);
composer.addPass(renderPass);

const bloomPass = new UnrealBloomPass(
  new THREE.Vector2(window.innerWidth, window.innerHeight),
  1.8,
  0.75,
  0.15
);
bloomPass.threshold = 0.12;
bloomPass.strength = 1.45;
bloomPass.radius = 0.65;
composer.addPass(bloomPass);

// ============================================================
// KIRA CINEMATIC NEURAL REACTOR — ENHANCED
// ============================================================

const reactor = new THREE.Group();
scene.add(reactor);
reactor.scale.setScalar(1.05);

// --- OUTER DARK METALLIC SHELL ---
const shellGeometry = new THREE.IcosahedronGeometry(2.3, 3);
const shellMaterial = new THREE.MeshStandardMaterial({
  color: 0x050505,
  metalness: 0.95,
  roughness: 0.25,
  emissive: 0x180000,
  emissiveIntensity: 0.2,
  transparent: true,
  opacity: 0.18,
  depthWrite: false,
});
const shell = new THREE.Mesh(shellGeometry, shellMaterial);
reactor.add(shell);

// --- RED HOLOGRAPHIC WIRE SHELL ---
const wireGeometry = new THREE.IcosahedronGeometry(2.35, 2);
const wireMaterial = new THREE.MeshBasicMaterial({
  color: 0xff1515,
  wireframe: true,
  transparent: true,
  opacity: 0.04,
});
const wireShell = new THREE.Mesh(wireGeometry, wireMaterial);
reactor.add(wireShell);

// --- HEXAGONAL ARMOR PLATES ---
const armorGroup = new THREE.Group();
reactor.add(armorGroup);

const armorMaterial = new THREE.MeshStandardMaterial({
  color: 0x090909,
  metalness: 1.0,
  roughness: 0.15,
  emissive: 0x250000,
  emissiveIntensity: 0.5,
});

const armorEdgeMaterial = new THREE.MeshBasicMaterial({
  color: 0xff1515,
  transparent: true,
  opacity: 0.6,
});

// Create hexagonal plates around the equator
for (let i = 0; i < 16; i++) {
  const angle = (i / 16) * Math.PI * 2;
  const hexShape = new THREE.Shape();
  const hexRadius = 0.35;
  for (let j = 0; j < 6; j++) {
    const a = (j / 6) * Math.PI * 2 - Math.PI / 6;
    const x = Math.cos(a) * hexRadius;
    const y = Math.sin(a) * hexRadius;
    if (j === 0) hexShape.moveTo(x, y);
    else hexShape.lineTo(x, y);
  }
  hexShape.closePath();

  const hexGeo = new THREE.ExtrudeGeometry(hexShape, { depth: 0.08, bevelEnabled: false });
  const hex = new THREE.Mesh(hexGeo, armorMaterial);
  hex.position.set(Math.cos(angle) * 1.75, Math.sin(angle) * 1.75, 0);
  hex.rotation.z = angle;
  hex.lookAt(0, 0, 0);
  armorGroup.add(hex);

  // Edge glow
  const edgeGeo = new THREE.EdgesGeometry(hexGeo);
  const edgeMat = new THREE.LineBasicMaterial({ color: 0xff2020, transparent: true, opacity: 0.7 });
  const edgeLine = new THREE.LineSegments(edgeGeo, edgeMat);
  edgeLine.position.copy(hex.position);
  edgeLine.rotation.copy(hex.rotation);
  armorGroup.add(edgeLine);
}

// Vertical armor fins
const verticalArmor = new THREE.Group();
reactor.add(verticalArmor);

for (let i = 0; i < 10; i++) {
  const angle = (i / 10) * Math.PI * 2;
  const finGeo = new THREE.BoxGeometry(0.06, 1.4, 0.25);
  const fin = new THREE.Mesh(finGeo, armorMaterial);
  fin.position.set(Math.cos(angle) * 2.0, 0, Math.sin(angle) * 2.0);
  fin.rotation.y = -angle;
  verticalArmor.add(fin);
}

// --- INNER ENERGY SPHERE ---
const energyGeometry = new THREE.SphereGeometry(1.55, 64, 64);
const energyMaterial = new THREE.MeshBasicMaterial({
  color: 0xff0808,
  transparent: true,
  opacity: 0.18,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});
const energySphere = new THREE.Mesh(energyGeometry, energyMaterial);
reactor.add(energySphere);

// --- NEURAL NETWORK NODES ---
const neuralNodes = [];
const neuralConnections = [];
const nodeGroup = new THREE.Group();
reactor.add(nodeGroup);

const nodeMaterial = new THREE.MeshBasicMaterial({
  color: 0xff3030,
  transparent: true,
  opacity: 0.9,
  blending: THREE.AdditiveBlending,
});

const nodeGlowMaterial = new THREE.MeshBasicMaterial({
  color: 0xff2020,
  transparent: true,
  opacity: 0.3,
  blending: THREE.AdditiveBlending,
});

// Create neural nodes at various positions
const nodePositions = [];
for (let i = 0; i < 24; i++) {
  const radius = 1.2 + Math.random() * 0.8;
  const theta = Math.random() * Math.PI * 2;
  const phi = Math.acos(2 * Math.random() - 1);
  const pos = new THREE.Vector3(
    radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.sin(phi) * Math.sin(theta),
    radius * Math.cos(phi)
  );
  nodePositions.push(pos);

  const nodeGeo = new THREE.SphereGeometry(0.06, 12, 12);
  const node = new THREE.Mesh(nodeGeo, nodeMaterial.clone());
  node.position.copy(pos);
  nodeGroup.add(node);
  neuralNodes.push(node);

  // Node glow
  const glowGeo = new THREE.SphereGeometry(0.12, 8, 8);
  const glow = new THREE.Mesh(glowGeo, nodeGlowMaterial.clone());
  glow.position.copy(pos);
  nodeGroup.add(glow);
  node.userData.glow = glow;
}

// Connect nearby nodes with energy lines
const lineMaterial = new THREE.LineBasicMaterial({
  color: 0xff1818,
  transparent: true,
  opacity: 0.25,
  blending: THREE.AdditiveBlending,
});

for (let i = 0; i < nodePositions.length; i++) {
  for (let j = i + 1; j < nodePositions.length; j++) {
    const dist = nodePositions[i].distanceTo(nodePositions[j]);
    if (dist < 1.5) {
      const lineGeo = new THREE.BufferGeometry().setFromPoints([nodePositions[i], nodePositions[j]]);
      const line = new THREE.Line(lineGeo, lineMaterial.clone());
      nodeGroup.add(line);
      neuralConnections.push({ line, dist, i, j });
    }
  }
}

// --- CORE ---
const coreGeometry = new THREE.SphereGeometry(0.45, 64, 64);
const coreMaterial = new THREE.MeshBasicMaterial({
  color: 0xffffff,
  toneMapped: false,
});
const core = new THREE.Mesh(coreGeometry, coreMaterial);
reactor.add(core);

// --- CORE RED GLOW ---
const glowGeometry = new THREE.SphereGeometry(0.82, 64, 64);
const glowMaterial = new THREE.MeshBasicMaterial({
  color: 0xff1515,
  transparent: true,
  opacity: 0.45,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
  toneMapped: false,
});
const coreGlow = new THREE.Mesh(glowGeometry, glowMaterial);
reactor.add(coreGlow);

// --- WHITE HOT CORE AURA ---
const whiteGlowGeometry = new THREE.SphereGeometry(0.65, 64, 64);
const whiteGlowMaterial = new THREE.MeshBasicMaterial({
  color: 0xffdddd,
  transparent: true,
  opacity: 0.3,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
  toneMapped: false,
});
const whiteGlow = new THREE.Mesh(whiteGlowGeometry, whiteGlowMaterial);
reactor.add(whiteGlow);

// --- CENTRAL NEURAL PROCESSOR ---
const neuralCore = new THREE.Group();
reactor.add(neuralCore);

const innerRingGeometry = new THREE.TorusGeometry(0.65, 0.04, 16, 96);
const innerRingMaterial = new THREE.MeshBasicMaterial({
  color: 0xff2020,
  transparent: true,
  opacity: 0.9,
  blending: THREE.AdditiveBlending,
});
const innerRing = new THREE.Mesh(innerRingGeometry, innerRingMaterial);
innerRing.rotation.x = Math.PI / 2;
neuralCore.add(innerRing);

const secondRingGeometry = new THREE.TorusGeometry(0.95, 0.02, 16, 128);
const secondRingMaterial = new THREE.MeshBasicMaterial({
  color: 0xff3030,
  transparent: true,
  opacity: 0.65,
  blending: THREE.AdditiveBlending,
});
const secondRing = new THREE.Mesh(secondRingGeometry, secondRingMaterial);
secondRing.rotation.x = Math.PI / 2;
neuralCore.add(secondRing);

// Third ring (tilted)
const thirdRingGeometry = new THREE.TorusGeometry(0.8, 0.015, 12, 96);
const thirdRingMaterial = new THREE.MeshBasicMaterial({
  color: 0xff4040,
  transparent: true,
  opacity: 0.5,
  blending: THREE.AdditiveBlending,
});
const thirdRing = new THREE.Mesh(thirdRingGeometry, thirdRingMaterial);
thirdRing.rotation.x = Math.PI / 3;
thirdRing.rotation.y = Math.PI / 4;
neuralCore.add(thirdRing);

const frameGeometry = new THREE.CylinderGeometry(0.5, 0.5, 0.18, 32);
const frameMaterial = new THREE.MeshStandardMaterial({
  color: 0x090909,
  metalness: 1,
  roughness: 0.15,
  emissive: 0x220000,
  emissiveIntensity: 0.35,
});
const coreFrame = new THREE.Mesh(frameGeometry, frameMaterial);
coreFrame.rotation.x = Math.PI / 2;
neuralCore.add(coreFrame);

const discGeometry = new THREE.CylinderGeometry(0.36, 0.36, 0.2, 64);
const discMaterial = new THREE.MeshBasicMaterial({
  color: 0xff0808,
  transparent: true,
  opacity: 1.0,
  blending: THREE.AdditiveBlending,
});
const energyDisc = new THREE.Mesh(discGeometry, discMaterial);
energyDisc.rotation.x = Math.PI / 2;
energyDisc.position.z = 0.12;
neuralCore.add(energyDisc);

// --- ROTATING NEURAL ORBITS ---
const neuralOrbit1 = new THREE.Group();
const neuralOrbit2 = new THREE.Group();
const neuralOrbit3 = new THREE.Group();
neuralCore.add(neuralOrbit1);
neuralCore.add(neuralOrbit2);
neuralCore.add(neuralOrbit3);

const neuralOrbitGeometry = new THREE.TorusGeometry(1.2, 0.014, 8, 128);
const neuralOrbitMaterial = new THREE.MeshBasicMaterial({
  color: 0xff1818,
  transparent: true,
  opacity: 0.55,
  blending: THREE.AdditiveBlending,
});

const neuralOrbitRing1 = new THREE.Mesh(neuralOrbitGeometry, neuralOrbitMaterial);
neuralOrbit1.add(neuralOrbitRing1);

const neuralOrbitRing2 = new THREE.Mesh(neuralOrbitGeometry, neuralOrbitMaterial.clone());
neuralOrbit2.add(neuralOrbitRing2);
neuralOrbitRing2.rotation.x = Math.PI / 2;
neuralOrbitRing2.rotation.z = Math.PI / 3;

const neuralOrbitRing3 = new THREE.Mesh(neuralOrbitGeometry, neuralOrbitMaterial.clone());
neuralOrbit3.add(neuralOrbitRing3);
neuralOrbitRing3.rotation.x = Math.PI / 4;
neuralOrbitRing3.rotation.y = Math.PI / 2;

// --- ENERGY BEAMS ---
const beamGroup = new THREE.Group();
reactor.add(beamGroup);

const beamMaterial = new THREE.MeshBasicMaterial({
  color: 0xff2020,
  transparent: true,
  opacity: 0.5,
  blending: THREE.AdditiveBlending,
});

for (let i = 0; i < 12; i++) {
  const angle = (i / 12) * Math.PI * 2;
  const beamGeometry = new THREE.BoxGeometry(0.02, 1.8, 0.02);
  const beam = new THREE.Mesh(beamGeometry, beamMaterial.clone());
  beam.position.set(Math.cos(angle) * 0.95, Math.sin(angle) * 0.95, 0);
  beam.rotation.z = angle;
  beamGroup.add(beam);
}

// --- ENERGY HALO ---
const haloGeometry = new THREE.RingGeometry(0.65, 0.88, 96);
const haloMaterial = new THREE.MeshBasicMaterial({
  color: 0xff2020,
  transparent: true,
  opacity: 0.35,
  side: THREE.DoubleSide,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});
const halo = new THREE.Mesh(haloGeometry, haloMaterial);
halo.rotation.x = Math.PI / 2;
reactor.add(halo);

// --- ENERGY ARCS (lightning-like connections) ---
const arcGroup = new THREE.Group();
reactor.add(arcGroup);

function createArc(start, end, segments = 20) {
  const points = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const x = start.x + (end.x - start.x) * t + (Math.random() - 0.5) * 0.3;
    const y = start.y + (end.y - start.y) * t + (Math.random() - 0.5) * 0.3;
    const z = start.z + (end.z - start.z) * t + (Math.random() - 0.5) * 0.3;
    points.push(new THREE.Vector3(x, y, z));
  }
  const geo = new THREE.BufferGeometry().setFromPoints(points);
  const mat = new THREE.LineBasicMaterial({
    color: 0xff4040,
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending,
  });
  return new THREE.Line(geo, mat);
}

const arcs = [];
for (let i = 0; i < 6; i++) {
  const angle1 = Math.random() * Math.PI * 2;
  const angle2 = angle1 + Math.PI * (0.5 + Math.random());
  const r = 1.5;
  const start = new THREE.Vector3(Math.cos(angle1) * r, Math.sin(angle1) * r, (Math.random() - 0.5) * 0.5);
  const end = new THREE.Vector3(Math.cos(angle2) * r, Math.sin(angle2) * r, (Math.random() - 0.5) * 0.5);
  const arc = createArc(start, end);
  arcGroup.add(arc);
  arcs.push({ mesh: arc, start, end, phase: Math.random() * Math.PI * 2 });
}

// --- POINT LIGHTS ---
const reactorLight = new THREE.PointLight(0xff1010, 12, 10);
reactorLight.position.set(0, 0, 0);
reactor.add(reactorLight);

const accentLight1 = new THREE.PointLight(0xff4040, 4, 8);
accentLight1.position.set(3, 2, 2);
reactor.add(accentLight1);

const accentLight2 = new THREE.PointLight(0xff0000, 3, 8);
accentLight2.position.set(-3, -2, 2);
reactor.add(accentLight2);

// --- ORBITAL RINGS ---
const ringMaterials = [];

function createReactorRing(radius, tube, rotation, opacity) {
  const geometry = new THREE.TorusGeometry(radius, tube, 16, 200);
  const material = new THREE.MeshBasicMaterial({
    color: 0xff1010,
    transparent: true,
    opacity: opacity,
  });
  const ring = new THREE.Mesh(geometry, material);
  ring.rotation.set(rotation.x, rotation.y, rotation.z);
  reactor.add(ring);
  ringMaterials.push(material);
  return ring;
}

const ring1 = createReactorRing(3.1, 0.014, new THREE.Euler(1.1, 0.15, 0.25), 0.3);
const ring2 = createReactorRing(2.8, 0.02, new THREE.Euler(0.25, 1.15, 0.5), 0.22);
const ring3 = createReactorRing(3.4, 0.01, new THREE.Euler(1.55, 0.55, 0.2), 0.16);
const ring4 = createReactorRing(2.5, 0.009, new THREE.Euler(0.4, 0.8, 1.2), 0.16);
const ring5 = createReactorRing(3.7, 0.007, new THREE.Euler(0.8, 0.3, 0.9), 0.1);
const ring6 = createReactorRing(2.2, 0.012, new THREE.Euler(1.3, 0.6, 0.4), 0.18);

// --- HOLOGRAPHIC DATA RING ---
const dataRingGroup = new THREE.Group();
reactor.add(dataRingGroup);

const dataRingGeo = new THREE.TorusGeometry(3.8, 0.005, 8, 256);
const dataRingMat = new THREE.MeshBasicMaterial({
  color: 0xff3030,
  transparent: true,
  opacity: 0.2,
});
const dataRing = new THREE.Mesh(dataRingGeo, dataRingMat);
dataRing.rotation.x = Math.PI / 2.2;
dataRingGroup.add(dataRing);

// Small data markers on the ring
for (let i = 0; i < 32; i++) {
  const angle = (i / 32) * Math.PI * 2;
  const markerGeo = new THREE.BoxGeometry(0.08, 0.08, 0.02);
  const markerMat = new THREE.MeshBasicMaterial({
    color: 0xff2020,
    transparent: true,
    opacity: 0.4 + Math.random() * 0.3,
    blending: THREE.AdditiveBlending,
  });
  const marker = new THREE.Mesh(markerGeo, markerMat);
  marker.position.set(Math.cos(angle) * 3.8, Math.sin(angle) * 3.8, 0);
  marker.rotation.z = angle;
  dataRingGroup.add(marker);
}

// --- ENERGY PARTICLES (flowing toward core) ---
const particleCount = 800;
const particlePositions = new Float32Array(particleCount * 3);
const particleVelocities = new Float32Array(particleCount * 3);
const particleColors = new Float32Array(particleCount * 3);

for (let i = 0; i < particleCount; i++) {
  const radius = 2.5 + Math.random() * 3.0;
  const theta = Math.random() * Math.PI * 2;
  const phi = Math.acos(2 * Math.random() - 1);
  particlePositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
  particlePositions[i * 3 + 1] = radius * Math.cos(phi);
  particlePositions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);

  // Velocity toward center with some randomness
  const speed = 0.005 + Math.random() * 0.01;
  particleVelocities[i * 3] = -particlePositions[i * 3] * speed;
  particleVelocities[i * 3 + 1] = -particlePositions[i * 3 + 1] * speed;
  particleVelocities[i * 3 + 2] = -particlePositions[i * 3 + 2] * speed;

  // Color variation (red to orange)
  const hue = 0.0 + Math.random() * 0.05;
  const color = new THREE.Color().setHSL(hue, 1, 0.5);
  particleColors[i * 3] = color.r;
  particleColors[i * 3 + 1] = color.g;
  particleColors[i * 3 + 2] = color.b;
}

const particleGeometry = new THREE.BufferGeometry();
particleGeometry.setAttribute("position", new THREE.BufferAttribute(particlePositions, 3));
particleGeometry.setAttribute("color", new THREE.BufferAttribute(particleColors, 3));

const particleMaterial = new THREE.PointsMaterial({
  size: 0.035,
  vertexColors: true,
  transparent: true,
  opacity: 0.5,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});

const reactorParticles = new THREE.Points(particleGeometry, particleMaterial);
reactor.add(reactorParticles);

// --- OUTER DUST FIELD ---
const dustCount = 300;
const dustPositions = new Float32Array(dustCount * 3);
const dustColors = new Float32Array(dustCount * 3);

for (let i = 0; i < dustCount; i++) {
  const radius = 4 + Math.random() * 4;
  const theta = Math.random() * Math.PI * 2;
  const phi = Math.acos(2 * Math.random() - 1);
  dustPositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
  dustPositions[i * 3 + 1] = radius * Math.cos(phi);
  dustPositions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);

  const c = new THREE.Color().setHSL(0, 0.8, 0.3 + Math.random() * 0.2);
  dustColors[i * 3] = c.r;
  dustColors[i * 3 + 1] = c.g;
  dustColors[i * 3 + 2] = c.b;
}

const dustGeo = new THREE.BufferGeometry();
dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPositions, 3));
dustGeo.setAttribute("color", new THREE.BufferAttribute(dustColors, 3));

const dustMat = new THREE.PointsMaterial({
  size: 0.02,
  vertexColors: true,
  transparent: true,
  opacity: 0.3,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});

const dustField = new THREE.Points(dustGeo, dustMat);
reactor.add(dustField);

/* =========================================================
   MATRIX RAIN — ENHANCED
   ========================================================= */

const matrixCanvas = document.getElementById("matrix");
const matrixContext = matrixCanvas.getContext("2d");
let matrixWidth = 0;
let matrixHeight = 0;

const matrixFontSize = 14;
const matrixChars = "01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEF<>{}[]|/\\=+-*&^%$#@!?";

let matrixColumns = [];
let matrixSpeeds = [];
let matrixBrightness = [];
let matrixTrails = [];

function resizeMatrix() {
  matrixWidth = matrixCanvas.width = window.innerWidth;
  matrixHeight = matrixCanvas.height = window.innerHeight;
  const columns = Math.floor(matrixWidth / matrixFontSize);
  
  matrixColumns = new Array(columns).fill(0).map(() => Math.random() * matrixHeight / matrixFontSize);
  matrixSpeeds = new Array(columns).fill(0).map(() => 0.5 + Math.random() * 1.5);
  matrixBrightness = new Array(columns).fill(0).map(() => Math.random());
  matrixTrails = new Array(columns).fill(0).map(() => 5 + Math.floor(Math.random() * 15));
}

function drawMatrix() {
  // Fade effect (creates trails)
  matrixContext.fillStyle = "rgba(0, 0, 0, 0.06)";
  matrixContext.fillRect(0, 0, matrixWidth, matrixHeight);
  
  matrixContext.font = `${matrixFontSize}px 'Courier New', monospace`;

  for (let i = 0; i < matrixColumns.length; i++) {
    const x = i * matrixFontSize;
    const y = matrixColumns[i] * matrixFontSize;
    
    // Random character
    const char = matrixChars[Math.floor(Math.random() * matrixChars.length)];
    
    // Brightness variation
    const brightness = matrixBrightness[i];
    
    // Leading character (brightest)
    if (brightness > 0.9) {
      matrixContext.fillStyle = "#ffffff";
      matrixContext.shadowBlur = 15;
      matrixContext.shadowColor = "#ff4040";
    } else if (brightness > 0.7) {
      matrixContext.fillStyle = "#ff6060";
      matrixContext.shadowBlur = 10;
      matrixContext.shadowColor = "#ff2020";
    } else if (brightness > 0.4) {
      matrixContext.fillStyle = "#d51b1b";
      matrixContext.shadowBlur = 5;
      matrixContext.shadowColor = "#ff1010";
    } else {
      matrixContext.fillStyle = "#8b1010";
      matrixContext.shadowBlur = 0;
    }
    
    matrixContext.fillText(char, x, y);
    matrixContext.shadowBlur = 0;
    
    // Occasional glitch effect
    if (Math.random() < 0.001) {
      matrixContext.fillStyle = "#ff8080";
      matrixContext.fillRect(x, y - matrixFontSize, matrixFontSize, matrixFontSize * 3);
    }
    
    // Move down
    if (y > matrixHeight && Math.random() > 0.96) {
      matrixColumns[i] = 0;
      matrixBrightness[i] = Math.random();
      matrixSpeeds[i] = 0.5 + Math.random() * 1.5;
      matrixTrails[i] = 5 + Math.floor(Math.random() * 15);
    } else {
      matrixColumns[i] += matrixSpeeds[i];
    }
  }
}

/* =========================================================
   ANIMATION
   ========================================================= */

const clock = new THREE.Clock();
let lastArcUpdate = 0;

function animate() {
  requestAnimationFrame(animate);
  const time = performance.now() * 0.001;

  // --- REACTOR ROTATION ---
  reactor.rotation.y = time * 0.1;
  reactor.rotation.x = Math.sin(time * 0.15) * 0.06;
  
  armorGroup.rotation.y = -time * 0.06;
  verticalArmor.rotation.y = time * 0.04;
  
  // --- HALO ---
  halo.rotation.z = time * 1.5;
  
  // --- NEURAL CORE ---
  neuralCore.rotation.z = time * 0.3;
  innerRing.rotation.z = time * 1.0;
  secondRing.rotation.z = -time * 0.7;
  thirdRing.rotation.x = time * 0.5;
  thirdRing.rotation.y = time * 0.3;
  
  // --- NEURAL ORBITS ---
  neuralOrbit1.rotation.x = time * 0.6;
  neuralOrbit1.rotation.y = time * 0.35;
  neuralOrbit2.rotation.x = -time * 0.45;
  neuralOrbit2.rotation.z = time * 0.7;
  neuralOrbit3.rotation.y = time * 0.55;
  neuralOrbit3.rotation.z = -time * 0.4;
  
  // --- ENERGY DISC ---
  energyDisc.scale.setScalar(1 + Math.sin(time * 3.5) * 0.1);
  
  // --- BEAMS ---
  beamGroup.rotation.z = -time * 0.2;
  beamGroup.children.forEach((beam, i) => {
    beam.material.opacity = 0.3 + Math.sin(time * 2 + i * 0.5) * 0.2;
  });
  
  // --- NEURAL NODES (pulsing) ---
  neuralNodes.forEach((node, i) => {
    const pulse = 0.8 + Math.sin(time * 3 + i * 0.3) * 0.2;
    node.scale.setScalar(pulse);
    node.material.opacity = 0.7 + Math.sin(time * 2.5 + i * 0.4) * 0.3;
    if (node.userData.glow) {
      node.userData.glow.scale.setScalar(pulse * 1.5);
      node.userData.glow.material.opacity = 0.2 + Math.sin(time * 2 + i * 0.5) * 0.15;
    }
  });
  
  // --- NEURAL CONNECTIONS (pulsing opacity) ---
  neuralConnections.forEach((conn, i) => {
    conn.line.material.opacity = 0.15 + Math.sin(time * 2 + i * 0.2) * 0.1;
  });
  
  // --- ENERGY ARCS (regenerate periodically) ---
  if (time - lastArcUpdate > 2) {
    lastArcUpdate = time;
    arcGroup.children.forEach((arc, i) => {
      const angle1 = Math.random() * Math.PI * 2;
      const angle2 = angle1 + Math.PI * (0.5 + Math.random());
      const r = 1.5;
      const start = new THREE.Vector3(Math.cos(angle1) * r, Math.sin(angle1) * r, (Math.random() - 0.5) * 0.5);
      const end = new THREE.Vector3(Math.cos(angle2) * r, Math.sin(angle2) * r, (Math.random() - 0.5) * 0.5);
      
      const points = [];
      for (let j = 0; j <= 20; j++) {
        const t = j / 20;
        const x = start.x + (end.x - start.x) * t + (Math.random() - 0.5) * 0.3;
        const y = start.y + (end.y - start.y) * t + (Math.random() - 0.5) * 0.3;
        const z = start.z + (end.z - start.z) * t + (Math.random() - 0.5) * 0.3;
        points.push(new THREE.Vector3(x, y, z));
      }
      
      arc.geometry.dispose();
      arc.geometry = new THREE.BufferGeometry().setFromPoints(points);
    });
  }
  
  // Arc opacity pulsing
  arcGroup.children.forEach((arc, i) => {
    arc.material.opacity = 0.3 + Math.sin(time * 4 + i) * 0.3;
  });
  
  // --- DATA RING ---
  dataRingGroup.rotation.z = time * 0.15;
  dataRingGroup.children.forEach((child, i) => {
    if (i > 0) { // Skip the ring itself, only animate markers
      child.material.opacity = 0.3 + Math.sin(time * 3 + i * 0.5) * 0.3;
    }
  });
  
  // --- ORBITAL RINGS ---
  ring1.rotation.z += 0.002;
  ring1.rotation.x += 0.0008;
  ring2.rotation.y += 0.0025;
  ring2.rotation.z -= 0.001;
  ring3.rotation.x -= 0.0012;
  ring3.rotation.y += 0.0015;
  ring4.rotation.z += 0.003;
  ring5.rotation.x += 0.001;
  ring5.rotation.y += 0.002;
  ring6.rotation.z -= 0.0025;
  
  // --- PULSING EFFECTS ---
  const energyPulse = 1 + Math.sin(time * 2.5) * 0.06;
  energySphere.scale.setScalar(energyPulse);
  
  const corePulse = 1 + Math.sin(time * 4) * 0.15;
  core.scale.setScalar(corePulse);
  
  const glowPulse = 1 + Math.sin(time * 3) * 0.18;
  coreGlow.scale.setScalar(glowPulse);
  
  const whitePulse = 1 + Math.sin(time * 4) * 0.12;
  whiteGlow.scale.setScalar(whitePulse);
  whiteGlowMaterial.opacity = 0.25 + Math.sin(time * 4) * 0.08;
  
  // --- LIGHTS ---
  reactorLight.intensity = 10 + Math.sin(time * 4) * 3;
  accentLight1.intensity = 3 + Math.sin(time * 2.5) * 1.5;
  accentLight2.intensity = 2.5 + Math.sin(time * 3) * 1.2;
  
  // --- FLOWING PARTICLES ---
  const positions = reactorParticles.geometry.attributes.position.array;
  for (let i = 0; i < particleCount; i++) {
    positions[i * 3] += particleVelocities[i * 3];
    positions[i * 3 + 1] += particleVelocities[i * 3 + 1];
    positions[i * 3 + 2] += particleVelocities[i * 3 + 2];
    
    // Reset when too close to center
    const dist = Math.sqrt(
      positions[i * 3] ** 2 + 
      positions[i * 3 + 1] ** 2 + 
      positions[i * 3 + 2] ** 2
    );
    
    if (dist < 0.5) {
      const radius = 2.5 + Math.random() * 3.0;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = radius * Math.cos(phi);
      positions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
      
      const speed = 0.005 + Math.random() * 0.01;
      particleVelocities[i * 3] = -positions[i * 3] * speed;
      particleVelocities[i * 3 + 1] = -positions[i * 3 + 1] * speed;
      particleVelocities[i * 3 + 2] = -positions[i * 3 + 2] * speed;
    }
  }
  reactorParticles.geometry.attributes.position.needsUpdate = true;
  
  // --- DUST FIELD ---
  dustField.rotation.y = time * 0.02;
  dustField.rotation.x = Math.sin(time * 0.1) * 0.1;
  
  // --- CAMERA PARALLAX ---
  camera.position.x = Math.sin(time * 0.1) * 0.5;
  camera.position.y = Math.cos(time * 0.08) * 0.3;
  camera.lookAt(0, 0, 0);
  
  // --- MATRIX RAIN ---
  drawMatrix();
  
  // --- RENDER ---
  composer.render();
}

/* =========================================================
   RESIZE
   ========================================================= */

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  composer.setSize(window.innerWidth, window.innerHeight);
});

/* =========================================================
   KIRA BACKEND INTEGRATION
   ========================================================= */

// Detect if running in pywebview (native app) or browser
const IS_NATIVE = typeof window.pywebview !== "undefined";
const API_BASE = window.location.protocol + "//" + window.location.hostname + ":8765";

// Set boot time
document.getElementById("boot-time").textContent = new Date().toTimeString().slice(0, 5);

// ─────────────────────────────────────────────
// Live Clock
// ─────────────────────────────────────────────

function updateClock() {
  const now = new Date();
  const timeEl = document.getElementById("clock-time");
  const dateEl = document.getElementById("clock-date");
  
  if (timeEl) {
    timeEl.textContent = now.toLocaleTimeString('en-US', { hour12: false });
  }
  
  if (dateEl) {
    dateEl.textContent = now.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    }).toUpperCase();
  }
}

updateClock();
setInterval(updateClock, 1000);

// Conversation management
function addMessage(sender, text, isUser = false) {
  const conversation = document.getElementById("conversation");
  const time = new Date().toTimeString().slice(0, 5);
  
  const block = document.createElement("div");
  block.className = isUser ? "message-block user-block" : "message-block";
  block.innerHTML = `
    <div class="message-meta ${isUser ? 'user' : ''}">${sender} &nbsp;//&nbsp; ${time}</div>
    <div class="message">${text}</div>
  `;
  
  conversation.appendChild(block);
  conversation.scrollTop = conversation.scrollHeight;
}

// Activity indicator
function setActivity(state) {
  const activityEl = document.getElementById("activity");
  const dotEl = document.getElementById("activity-dot");
  
  activityEl.textContent = state;
  dotEl.className = "activity-dot";
  
  if (state === "THINKING") {
    dotEl.classList.add("thinking");
  } else if (state === "SPEAKING") {
    dotEl.classList.add("speaking");
  } else if (state !== "STANDBY") {
    dotEl.classList.add("active");
  }
}

// ─────────────────────────────────────────────
// Text-to-Speech (KIRA speaks responses aloud using neural voices)
// ─────────────────────────────────────────────

let speechEnabled = true;
let currentAudio = null;

async function speak(text) {
  if (!speechEnabled || !text) return;
  
  // Stop any ongoing speech
  stopSpeaking();
  
  // Clean text for speech (remove markdown, URLs, code)
  const cleanText = text
    .replace(/```[\s\S]*?```/g, "code block")
    .replace(/`[^`]+`/g, "")
    .replace(/https?:\/\/\S+/g, "link")
    .replace(/[*_~]/g, "")
    .trim();
  
  if (!cleanText) return;
  
  try {
    setActivity("THINKING");
    console.log("[KIRA] Generating speech:", cleanText.substring(0, 60) + "...");
    
    // Call TTS API endpoint
    const response = await fetch(`${API_BASE}/api/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        text: cleanText,
        voice: "jenny"  // Use Jenny neural voice
      }),
    });
    
    if (!response.ok) {
      throw new Error(`TTS API error: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (data.error) {
      console.error("[KIRA] TTS error:", data.error);
      console.log("[KIRA] Falling back to browser TTS...");
      fallbackSpeak(cleanText);
      return;
    }
    
    if (!data.audio) {
      console.error("[KIRA] No audio data received");
      console.log("[KIRA] Falling back to browser TTS...");
      fallbackSpeak(cleanText);
      return;
    }
    
    // Decode base64 audio and play
    const audioBlob = base64ToBlob(data.audio, "audio/mpeg");
    const audioUrl = URL.createObjectURL(audioBlob);
    
    currentAudio = new Audio(audioUrl);
    
    currentAudio.onplay = () => {
      setActivity("SPEAKING");
      console.log("[KIRA] Speaking (neural voice)...");
    };
    
    currentAudio.onended = () => {
      setActivity("READY");
      URL.revokeObjectURL(audioUrl);
      currentAudio = null;
    };
    
    currentAudio.onerror = (event) => {
      console.error("[KIRA] Audio playback error:", event);
      console.log("[KIRA] Falling back to browser TTS...");
      fallbackSpeak(cleanText);
      URL.revokeObjectURL(audioUrl);
      currentAudio = null;
    };
    
    await currentAudio.play();
    
  } catch (error) {
    console.error("[KIRA] TTS failed:", error);
    console.log("[KIRA] Falling back to browser TTS...");
    fallbackSpeak(cleanText);
  }
}

// Fallback to browser Web Speech API if neural TTS fails
function fallbackSpeak(text) {
  if (!window.speechSynthesis) {
    console.error("[KIRA] No TTS available");
    setActivity("READY");
    return;
  }
  
  const utterance = new SpeechSynthesisUtterance(text);
  
  // Configure voice - fluent female
  utterance.rate = 0.95;
  utterance.pitch = 1.1;
  utterance.volume = 1.0;
  
  // Find the best female voice
  const voices = window.speechSynthesis.getVoices();
  const preferredVoice = voices.find(v => 
    v.lang.startsWith('en') && 
    (v.name.includes('Female') || v.name.includes('Samantha') || v.name.includes('Zira'))
  ) || voices.find(v => v.lang.startsWith('en'));
  
  if (preferredVoice) {
    utterance.voice = preferredVoice;
  }
  
  utterance.onstart = () => {
    setActivity("SPEAKING");
    console.log("[KIRA] Speaking (browser fallback)...");
  };
  
  utterance.onend = () => {
    setActivity("READY");
  };
  
  utterance.onerror = (event) => {
    console.error("[KIRA] Browser TTS error:", event.error);
    setActivity("READY");
  };
  
  window.speechSynthesis.speak(utterance);
}

function stopSpeaking() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }
  setActivity("READY");
}

// Helper: Convert base64 to Blob
function base64ToBlob(base64, mimeType) {
  const byteCharacters = atob(base64);
  const byteNumbers = new Array(byteCharacters.length);
  for (let i = 0; i < byteCharacters.length; i++) {
    byteNumbers[i] = byteCharacters.charCodeAt(i);
  }
  const byteArray = new Uint8Array(byteNumbers);
  return new Blob([byteArray], { type: mimeType });
}


// Mute/unmute toggle
const muteButton = document.getElementById("mute");
if (muteButton) {
  muteButton.addEventListener("click", () => {
    speechEnabled = !speechEnabled;
    
    // Update icon
    if (speechEnabled) {
      muteButton.innerHTML = `
        <svg viewBox="0 0 24 24">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
        </svg>
      `;
      muteButton.title = "Voice output ON";
    } else {
      muteButton.innerHTML = `
        <svg viewBox="0 0 24 24">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
          <line x1="23" y1="9" x2="17" y2="15"></line>
          <line x1="17" y1="9" x2="23" y2="15"></line>
        </svg>
      `;
      muteButton.title = "Voice output OFF";
    }
    
    if (!speechEnabled) {
      stopSpeaking();
    }
    
    console.log(`[KIRA] Voice output ${speechEnabled ? "enabled" : "disabled"}`);
  });
}

// Send command to backend (works in both native and browser modes)
async function sendCommand(text) {
  if (!text.trim()) return;
  
  addMessage("YOU", text, true);
  setActivity("THINKING");
  
  try {
    // Always use HTTP API — works in both native app and browser
    const response = await fetch(`${API_BASE}/api/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    
    if (data.error) {
      addMessage("SYSTEM", `Error: ${data.error}`);
    } else if (data.response) {
      addMessage("KIRA", data.response);
      speak(data.response);
    } else if (data.action && data.success) {
      addMessage("KIRA", `Done: ${data.action}`);
      speak(`Done. ${data.action.replace(/_/g, ' ')}`);
    } else if (data.action) {
      addMessage("KIRA", `Executed: ${data.action}`);
    } else {
      addMessage("KIRA", "Done.");
    }
    
    setActivity("READY");
  } catch (error) {
    console.error("Command failed:", error);
    
    if (error.message.includes("Failed to fetch") || error.message.includes("NetworkError") || error.message.includes("fetch")) {
      addMessage("SYSTEM", "Cannot reach KIRA backend at " + API_BASE + ". Check that the API server is running.");
    } else {
      addMessage("SYSTEM", `Error: ${error.message}`);
    }
    
    setActivity("ERROR");
    setTimeout(() => setActivity("READY"), 3000);
  }
}

// Command input handling
const commandInput = document.getElementById("command");
const sendButton = document.getElementById("send");

sendButton.addEventListener("click", () => {
  sendCommand(commandInput.value);
  commandInput.value = "";
});

commandInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    sendCommand(commandInput.value);
    commandInput.value = "";
  }
});

// Quick command function (exposed globally for onclick)
window.quickCmd = function(cmd) {
  commandInput.value = cmd;
  sendCommand(cmd);
  commandInput.value = "";
};

// Voice input (Web Speech API)
const micButton = document.getElementById("mic");
let recognition = null;

if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = "en-US";
  
  recognition.onstart = () => {
    micButton.classList.add("listening");
    setActivity("LISTENING");
  };
  
  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    commandInput.value = transcript;
    sendCommand(transcript);
    commandInput.value = "";
  };
  
  recognition.onend = () => {
    micButton.classList.remove("listening");
    setActivity("READY");
  };
  
  recognition.onerror = (event) => {
    console.error("Speech recognition error:", event.error);
    micButton.classList.remove("listening");
    setActivity("ERROR");
  };
  
  micButton.addEventListener("click", () => {
    if (recognition) {
      recognition.start();
    }
  });
} else {
  micButton.style.display = "none";
}

// Poll system telemetry every 3 seconds
async function updateTelemetry() {
  try {
    let data;
    
    if (IS_NATIVE && window.pywebview && window.pywebview.api) {
      data = await window.pywebview.api.get_system_info();
    } else {
      const response = await fetch(`${API_BASE}/api/system`);
      data = await response.json();
    }
    
    if (data.cpu_percent !== undefined) {
      document.getElementById("cpu").textContent = `${data.cpu_percent}%`;
      const cpuBar = document.getElementById("cpu-bar");
      if (cpuBar) cpuBar.style.width = `${data.cpu_percent}%`;
    }
    if (data.memory_percent !== undefined) {
      document.getElementById("memory").textContent = `${data.memory_percent}%`;
      const memBar = document.getElementById("memory-bar");
      if (memBar) memBar.style.width = `${data.memory_percent}%`;
    }
    if (data.gpu) {
      document.getElementById("gpu").textContent = data.gpu;
    }
  } catch (error) {
    // Backend not available
  }
}

// Poll tasks every 5 seconds
async function updateTasks() {
  try {
    let data;
    
    if (IS_NATIVE && window.pywebview && window.pywebview.api) {
      data = await window.pywebview.api.get_tasks();
    } else {
      const response = await fetch(`${API_BASE}/api/tasks?type=todo&completed=false`);
      data = await response.json();
    }
    
    const tasksList = document.getElementById("tasks-list");
    
    if (data.tasks && data.tasks.length > 0) {
      tasksList.innerHTML = data.tasks.slice(0, 5).map(task => `
        <div class="task-item">
          <span class="task-bullet"></span>
          <span>${task.title}</span>
        </div>
      `).join("");
    } else {
      tasksList.innerHTML = '<div class="task-empty">No pending tasks</div>';
    }
  } catch (error) {
    // Backend not available
  }
}

setInterval(updateTelemetry, 3000);
setInterval(updateTasks, 5000);
updateTelemetry();
updateTasks();

/* =========================================================
   START
   ========================================================= */

resizeMatrix();
animate();
