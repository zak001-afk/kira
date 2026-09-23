import * as THREE from "three";
import { SpeechPlayer } from "./speech.mjs?v=speech-sync-2";
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
// KIRA CINEMATIC NEURAL REACTOR
// ============================================================

const reactor = new THREE.Group();
scene.add(reactor);
reactor.scale.setScalar(1.05);

// --- OUTER SHELL ---
const shellGeometry = new THREE.SphereGeometry(2.25, 64, 64);
const shellMaterial = new THREE.MeshStandardMaterial({
  color: 0x050505,
  metalness: 0.95,
  roughness: 0.25,
  emissive: 0x180000,
  emissiveIntensity: 0.18,
  transparent: true,
  opacity: 0.2,
  depthWrite: false,
});
const shell = new THREE.Mesh(shellGeometry, shellMaterial);
reactor.add(shell);

// --- WIREFRAME SHELL ---
const wireGeometry = new THREE.SphereGeometry(2.3, 32, 32);
const wireMaterial = new THREE.MeshBasicMaterial({
  color: 0xff1515,
  wireframe: true,
  transparent: true,
  opacity: 0.035,
});
const wireShell = new THREE.Mesh(wireGeometry, wireMaterial);
reactor.add(wireShell);

// --- ARMOR RING (equator plates) ---
const armorGroup = new THREE.Group();
reactor.add(armorGroup);

const armorMaterial = new THREE.MeshStandardMaterial({
  color: 0x090909,
  metalness: 1.0,
  roughness: 0.18,
  emissive: 0x250000,
  emissiveIntensity: 0.45,
});

for (let i = 0; i < 12; i++) {
  const angle = (i / 12) * Math.PI * 2;
  const plateGeo = new THREE.BoxGeometry(0.95, 0.12, 0.38);
  const plate = new THREE.Mesh(plateGeo, armorMaterial);
  plate.position.set(Math.cos(angle) * 1.72, Math.sin(angle) * 1.72, 0);
  plate.rotation.z = angle;
  armorGroup.add(plate);
}

// --- VERTICAL ARMOR ---
const verticalArmor = new THREE.Group();
reactor.add(verticalArmor);

for (let i = 0; i < 8; i++) {
  const angle = (i / 8) * Math.PI * 2;
  const plateGeo = new THREE.BoxGeometry(0.32, 1.15, 0.1);
  const plate = new THREE.Mesh(plateGeo, armorMaterial);
  plate.position.set(Math.cos(angle) * 1.95, 0, Math.sin(angle) * 1.95);
  plate.rotation.y = -angle;
  verticalArmor.add(plate);
}

// =========================================================
// KIRA VISAGE HOLOGRAMME -- REMPLACE LE NOYAU / REACTEUR
// Le noyau energétique sphérique est remplacé par le visage de KIRA
// à la place exacte du noyau. Les anneaux extérieurs restent comme cadre.
// =========================================================
const voiceUniforms = {
  voiceTime: { value: 0 },
  voiceEnergy: { value: 0 },
  voiceLow: { value: 0 },
  voiceHigh: { value: 0 },
};

// -- Chargement texture visage --
const textureLoader = new THREE.TextureLoader();
const faceTexture = textureLoader.load('./kira_face.png', (tex) => {
  tex.colorSpace = THREE.SRGBColorSpace;
  try { tex.anisotropy = renderer.capabilities.getMaxAnisotropy(); } catch {}
});
faceTexture.colorSpace = THREE.SRGBColorSpace;

const faceGroup = new THREE.Group();
reactor.add(faceGroup);

// Halo lumineux derrière le visage (remplace coreGlow/whiteGlow)
const faceBackGlowGeo = new THREE.CircleGeometry(1.75, 64);
const faceBackGlowMat = new THREE.MeshBasicMaterial({
  color: 0xff1515,
  transparent: true,
  opacity: 0.15,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});
const faceBackGlow = new THREE.Mesh(faceBackGlowGeo, faceBackGlowMat);
faceBackGlow.position.z = 0.34;
faceGroup.add(faceBackGlow);

const faceBackGlow2Geo = new THREE.CircleGeometry(2.08, 64);
const faceBackGlow2Mat = new THREE.MeshBasicMaterial({
  color: 0x220505,
  transparent: true,
  opacity: 0.32,
  side: THREE.DoubleSide,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});
const faceBackGlow2 = new THREE.Mesh(faceBackGlow2Geo, faceBackGlow2Mat);
faceBackGlow2.position.z = 0.30;
faceGroup.add(faceBackGlow2);

// Visage - Shader holographique avec synchro voix (bouche/yeux réagissent)
const faceUniforms = {
  tFace: { value: faceTexture },
  time: { value: 0 },
  energy: { value: 0 },
  low: { value: 0 },
  high: { value: 0 },
};

const faceGeo = new THREE.CircleGeometry(1.48, 96);
const faceMat = new THREE.ShaderMaterial({
  uniforms: faceUniforms,
  transparent: true,
  depthWrite: false,
  vertexShader: `
    varying vec2 vUv;
    void main(){
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
    }
  `,
  fragmentShader: `
    uniform sampler2D tFace;
    uniform float time;
    uniform float energy;
    uniform float low;
    uniform float high;
    varying vec2 vUv;
    void main(){
      vec2 uv = vUv;
      // micro ondulation voix - simulacre de mouvement bouche/joues
      uv.x += sin(uv.y * 28.0 + time * 7.0) * energy * 0.013;
      uv.y += cos(uv.x * 22.0 - time * 5.0) * low * 0.011;
      // petit glitch horizontal sur les aigus (consonnes)
      uv.x += high * 0.015 * sin(time * 50.0 + uv.y * 60.0);
      vec4 col = texture2D(tFace, uv);
      // masque circulaire doux (vignette holographique)
      vec2 c = uv - 0.5;
      float r = length(c) * 2.0;
      float mask = 1.0 - smoothstep(0.88, 1.03, r);
      // scanlines holographiques subtiles
      float scan = 0.92 + 0.08 * sin(uv.y * 420.0 - time * 35.0);
      // flicker & boost selon voix
      float flick = 1.0 + energy * 0.45 + low * 0.25;
      float edge = smoothstep(0.82, 1.0, r);
      vec3 edgeCol = vec3(1.0, 0.18, 0.18) * edge * 0.55;
      col.rgb = col.rgb * flick * scan + edgeCol;
      col.rgb += high * 0.28;
      col.rgb += edge * 0.12;
      col.a *= mask * (0.98 + energy * 0.07);
      if(col.a < 0.02) discard;
      gl_FragColor = col;
    }
  `,
});
const faceMesh = new THREE.Mesh(faceGeo, faceMat);
faceMesh.position.z = 0.52;
faceGroup.add(faceMesh);

// Reflet vitreux devant (légère brillance holographique)
const faceGlassGeo = new THREE.CircleGeometry(1.50, 64);
const faceGlassMat = new THREE.MeshBasicMaterial({
  color: 0xffffff,
  transparent: true,
  opacity: 0.035,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});
const faceGlass = new THREE.Mesh(faceGlassGeo, faceGlassMat);
faceGlass.position.z = 0.56;
faceGroup.add(faceGlass);

// Cadres holographiques autour du visage (remplace innerRing/secondRing d'origine)
// On garde les mêmes noms de variables pour compatibilité avec l'animation
const neuralCore = new THREE.Group();
reactor.add(neuralCore);

const innerRingGeo = new THREE.TorusGeometry(1.60, 0.028, 12, 96);
const innerRingMat = new THREE.MeshBasicMaterial({
  color: 0xff2020,
  transparent: true,
  opacity: 0.88,
  blending: THREE.AdditiveBlending,
});
const innerRing = new THREE.Mesh(innerRingGeo, innerRingMat);
innerRing.rotation.x = Math.PI / 2;
neuralCore.add(innerRing);

const secondRingGeo = new THREE.TorusGeometry(1.84, 0.016, 12, 128);
const secondRingMat = new THREE.MeshBasicMaterial({
  color: 0xff3030,
  transparent: true,
  opacity: 0.55,
  blending: THREE.AdditiveBlending,
});
const secondRing = new THREE.Mesh(secondRingGeo, secondRingMat);
secondRing.rotation.x = Math.PI / 2;
neuralCore.add(secondRing);

// Objets fantômes pour compatibilité animation (les anciens core/energySphere n'existent plus mais l'anim y fait encore référence)
const energySphere = { scale: new THREE.Vector3(1,1,1) };
const core = { scale: new THREE.Vector3(1,1,1) };
const coreGlow = faceBackGlow;
const glowMaterial = faceBackGlowMat;
const whiteGlow = faceBackGlow2;
const whiteGlowMaterial = faceBackGlow2Mat;
const energyDisc = { scale: { setScalar: ()=>{} }, rotation: {x:0} };


// --- NEURAL ORBITS ---
const neuralOrbit1 = new THREE.Group();
const neuralOrbit2 = new THREE.Group();
neuralCore.add(neuralOrbit1);
neuralCore.add(neuralOrbit2);

const orbitGeo = new THREE.TorusGeometry(1.15, 0.012, 8, 128);
const orbitMat = new THREE.MeshBasicMaterial({
  color: 0xff1818,
  transparent: true,
  opacity: 0.55,
  blending: THREE.AdditiveBlending,
});

const orbitRing1 = new THREE.Mesh(orbitGeo, orbitMat);
neuralOrbit1.add(orbitRing1);

const orbitRing2 = new THREE.Mesh(orbitGeo, orbitMat.clone());
neuralOrbit2.add(orbitRing2);
orbitRing2.rotation.x = Math.PI / 2;
orbitRing2.rotation.z = Math.PI / 3;

// --- ENERGY BEAMS ---
const beamGroup = new THREE.Group();
reactor.add(beamGroup);

const beamMat = new THREE.MeshBasicMaterial({
  color: 0xff2020,
  transparent: true,
  opacity: 0.45,
  blending: THREE.AdditiveBlending,
});

for (let i = 0; i < 8; i++) {
  const angle = (i / 8) * Math.PI * 2;
  const beamGeo = new THREE.BoxGeometry(0.025, 1.7, 0.025);
  const beam = new THREE.Mesh(beamGeo, beamMat);
  beam.position.set(Math.cos(angle) * 0.95, Math.sin(angle) * 0.95, 0);
  beam.rotation.z = angle;
  beamGroup.add(beam);
}

// --- ENERGY HALO ---
const haloGeo = new THREE.RingGeometry(0.62, 0.82, 96);
const haloMat = new THREE.MeshBasicMaterial({
  color: 0xff2020,
  transparent: true,
  opacity: 0.35,
  side: THREE.DoubleSide,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});
const halo = new THREE.Mesh(haloGeo, haloMat);
halo.rotation.x = Math.PI / 2;
reactor.add(halo);

// --- REACTOR LIGHT ---
const reactorLight = new THREE.PointLight(0xff1010, 11, 8);
reactorLight.position.set(0, 0, 0);
reactor.add(reactorLight);

// --- ORBITAL RINGS ---
function createReactorRing(radius, tube, rotation, opacity) {
  const geo = new THREE.TorusGeometry(radius, tube, 12, 180);
  const mat = new THREE.MeshBasicMaterial({
    color: 0xff1010,
    transparent: true,
    opacity: opacity,
  });
  const ring = new THREE.Mesh(geo, mat);
  ring.rotation.set(rotation.x, rotation.y, rotation.z);
  reactor.add(ring);
  return ring;
}

const ring1 = createReactorRing(3.05, 0.012, new THREE.Euler(1.1, 0.15, 0.25), 0.28);
const ring2 = createReactorRing(2.75, 0.018, new THREE.Euler(0.25, 1.15, 0.5), 0.2);
const ring3 = createReactorRing(3.35, 0.009, new THREE.Euler(1.55, 0.55, 0.2), 0.14);
const ring4 = createReactorRing(2.45, 0.008, new THREE.Euler(0.4, 0.8, 1.2), 0.14);

// --- PARTICLES ---
const particleCount = 450;
const particlePositions = new Float32Array(particleCount * 3);

for (let i = 0; i < particleCount; i++) {
  const radius = 2.4 + Math.random() * 2.2;
  const theta = Math.random() * Math.PI * 2;
  const phi = Math.acos(2 * Math.random() - 1);
  particlePositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
  particlePositions[i * 3 + 1] = radius * Math.cos(phi);
  particlePositions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
}

const particleGeo = new THREE.BufferGeometry();
particleGeo.setAttribute("position", new THREE.BufferAttribute(particlePositions, 3));

const particleMat = new THREE.PointsMaterial({
  color: 0xff2020,
  size: 0.025,
  transparent: true,
  opacity: 0.38,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});

const reactorParticles = new THREE.Points(particleGeo, particleMat);
reactor.add(reactorParticles);

/* =========================================================
   MATRIX RAIN
   ========================================================= */

const matrixCanvas = document.getElementById("matrix");
const matrixContext = matrixCanvas.getContext("2d");
let matrixWidth = 0;
let matrixHeight = 0;

const matrixFontSize = 16;
const matrixChars = "01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEF";

let matrixColumns = [];
let matrixSpeeds = [];
let matrixBrightness = [];

function resizeMatrix() {
  matrixWidth = matrixCanvas.width = window.innerWidth;
  matrixHeight = matrixCanvas.height = window.innerHeight;
  const columns = Math.floor(matrixWidth / matrixFontSize);
  
  matrixColumns = new Array(columns).fill(0).map(() => Math.random() * matrixHeight / matrixFontSize);
  matrixSpeeds = new Array(columns).fill(0).map(() => 0.15 + Math.random() * 0.4);
  matrixBrightness = new Array(columns).fill(0).map(() => Math.random());
}

function drawMatrix() {
  // Heavier fade for subtler trails
  matrixContext.fillStyle = "rgba(0, 0, 0, 0.08)";
  matrixContext.fillRect(0, 0, matrixWidth, matrixHeight);
  
  matrixContext.font = `${matrixFontSize}px 'Courier New', monospace`;

  for (let i = 0; i < matrixColumns.length; i++) {
    // Skip some columns for less density
    if (i % 3 === 0) continue;
    
    const x = i * matrixFontSize;
    const y = matrixColumns[i] * matrixFontSize;
    
    // Random character
    const char = matrixChars[Math.floor(Math.random() * matrixChars.length)];
    
    // Brightness variation (less intense)
    const brightness = matrixBrightness[i];
    
    // Simpler color scheme, less glow
    if (brightness > 0.85) {
      matrixContext.fillStyle = "#ff5555";
    } else if (brightness > 0.6) {
      matrixContext.fillStyle = "#cc2222";
    } else {
      matrixContext.fillStyle = "#661111";
    }
    
    matrixContext.fillText(char, x, y);
    
    // Reset when off screen (less frequent)
    if (y > matrixHeight && Math.random() > 0.985) {
      matrixColumns[i] = 0;
      matrixBrightness[i] = Math.random();
      matrixSpeeds[i] = 0.15 + Math.random() * 0.4;
    } else {
      matrixColumns[i] += matrixSpeeds[i];
    }
  }
}

/* =========================================================
   ANIMATION
   ========================================================= */

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let motionPreference = "auto";
try {
  const saved = localStorage.getItem("kira.motion");
  if (["auto", "on", "off"].includes(saved)) motionPreference = saved;
} catch { /* private/embedded browsers may block storage */ }
const motionButton = document.getElementById("motion-toggle");
const motionStatus = document.getElementById("motion-status");
const voiceMeter = document.getElementById("voice-level");
const motionTest = document.getElementById("motion-test");
const voiceTest = document.getElementById("voice-test");
let motionDemoStarted = -Infinity;
function motionDisabled() {
  return motionPreference === "off" || (motionPreference === "auto" && reducedMotion.matches);
}
function updateMotionButton() {
  motionButton.textContent = `MOTION: ${motionPreference.toUpperCase()}`;
  motionButton.title = "Auto follows Windows reduced motion. On explicitly enables movement. Off keeps it still.";
}
motionButton.addEventListener("click", () => {
  const choices = ["auto", "on", "off"];
  motionPreference = choices[(choices.indexOf(motionPreference) + 1) % choices.length];
  try { localStorage.setItem("kira.motion", motionPreference); } catch { /* optional */ }
  updateMotionButton();
});
motionTest.addEventListener("click", () => { motionDemoStarted = performance.now(); });
voiceTest.addEventListener("click", () => {
  if (!speech.enabled) return;
  speech.unlock();
  speak("My core moves with my voice. A short pause. Now I am speaking again.");
});
updateMotionButton();
let lastFrame = performance.now();
let voiceRotation = 0;

function animate() {
  requestAnimationFrame(animate);
  const now = performance.now();
  const time = now * 0.001;
  const dt = Math.min((now - lastFrame) / 1000, 0.1);
  lastFrame = now;
  const voice = speech.motion.sample(now);
  const disabled = motionDisabled();
  const demoAge = (now - motionDemoStarted) / 1000;
  const demo = demoAge >= 0 && demoAge < 3;
  const demoEnergy = demo ? Math.sin(demoAge * Math.PI / 3) * (0.35 + 0.6 * Math.sin(demoAge * 9) ** 2) : 0;
  const level = demo ? demoEnergy : voice.energy;
  voiceMeter.style.transform = `scaleX(${voice.energy.toFixed(3)})`;
  const label = disabled ? (motionPreference === "auto" ? "MOTION OFF · SYSTEM SETTING" : "MOTION OFF")
    : demo ? "TEST MOTION · NO AUDIO"
    : !speech.enabled ? "VOICE MUTED"
    : !voice.active ? (speechState === "THINKING" ? "WAITING FOR VOICE" : "VOICE IDLE")
    : voice.source === "audio" ? (voice.energy > 0.015 ? "VOICE SYNC · AUDIO" : "VOICE SYNC · QUIET / NO SIGNAL")
    : voice.source === "words" ? "VOICE SYNC · WORD TIMING" : "VOICE SYNC · ESTIMATED";
  if (motionStatus.textContent !== label) motionStatus.textContent = label;
  // Reduced motion keeps a quiet brightness cue, not speech-driven movement.
  const energy = disabled ? 0 : level;
  const low = disabled ? 0 : demo ? demoEnergy * 0.6 : voice.low;
  const high = disabled ? 0 : demo ? demoEnergy * 0.3 : voice.high;
  const light = level * (disabled ? 0.12 : 1);
  const motionTime = disabled ? 0 : time;
  const step = disabled ? 0 : dt;
  voiceRotation += energy * step;
  voiceUniforms.voiceTime.value = motionTime;
  voiceUniforms.voiceEnergy.value = energy;
  voiceUniforms.voiceLow.value = low;
  voiceUniforms.voiceHigh.value = high;
  // synchro visage
  faceUniforms.time.value = motionTime;
  faceUniforms.energy.value = energy;
  faceUniforms.low.value = low;
  faceUniforms.high.value = high;

  // Visage holographique : respirations subtiles, suit la voix
  reactor.rotation.y = motionTime * 0.09;
  reactor.rotation.x = Math.sin(motionTime * 0.14) * 0.06;
  // le visage respire légèrement avec la voix (échelle verticale = bouche qui s'ouvre)
  const breath = Math.sin(motionTime * 1.9) * 0.015;
  reactor.scale.set(1.05 + energy * 0.10, 1.05 + energy * 0.18 + breath*0.4, 1.05 + energy * 0.10);
  reactor.position.y = Math.sin(motionTime * 2.8) * energy * 0.10;
  armorGroup.rotation.y = -motionTime * 0.06;
  verticalArmor.rotation.y = motionTime * 0.04;
  halo.rotation.z = motionTime * 1.4 + voiceRotation * 0.4;
  halo.scale.setScalar(1 + low * 0.22);
  haloMat.opacity = 0.30 + light * 0.14;
  neuralCore.rotation.z = motionTime * 0.28 + voiceRotation * 0.45;
  neuralCore.scale.setScalar(1 + energy * 0.14);
  innerRing.rotation.z = motionTime * 0.9 + voiceRotation * 0.8;
  innerRing.scale.setScalar(1 + high * 0.20);
  secondRing.rotation.z = -motionTime * 0.6 - voiceRotation * 0.55;
  secondRing.scale.setScalar(1 + low * 0.16);
  neuralOrbit1.rotation.x = motionTime * 0.55 + voiceRotation * 0.8;
  neuralOrbit1.rotation.y = motionTime * 0.32;
  neuralOrbit2.rotation.x = -motionTime * 0.42;
  neuralOrbit2.rotation.z = motionTime * 0.65 + voiceRotation * 0.7;
  // plus de disc energie - remplacé par micro mouvement du visage
  faceGroup.rotation.z = Math.sin(motionTime * 0.9) * 0.02 + voiceRotation * 0.05;
  faceMesh.scale.set(1 + breath*0.5 + energy*0.06, 1 + energy*0.12 + high*0.04, 1);
  // la bouche/menton s'étire verticalement sur les voyelles (low), les aigus font briller
  faceGlass.scale.setScalar(1 + low*0.04);
  beamGroup.rotation.z = -motionTime * 0.20;
  beamGroup.scale.setScalar(1 + low * 0.10);
  beamMat.opacity = 0.32 + light * 0.12;

  // Frame-rate independent ring movement.
  ring1.rotation.z += step * 0.12;
  ring1.rotation.x += step * 0.05;
  ring2.rotation.y += step * 0.15;
  ring2.rotation.z -= step * 0.060;
  ring3.rotation.x -= step * 0.075;
  ring3.rotation.y += step * 0.090;
  ring4.rotation.z += step * 0.18;

  // Halo visage - pulse avec voix
  faceBackGlow.scale.setScalar(1 + breath + energy * 0.22);
  glowMaterial.opacity = 0.15 + light * 0.10 + high*0.04;
  faceBackGlow2.scale.setScalar(1 + breath*0.7 + high * 0.18 + energy * 0.08);
  whiteGlowMaterial.opacity = 0.28 + light * 0.06;
  // éclairage ponctuel du visage pulse avec la voix
  reactorLight.intensity = 7 + light * 4 + high*2;
  reactorLight.color.setHSL(0.0, 1.0, 0.55 + light*0.1);
  bloomPass.strength = 1.20 + light * 0.22 + energy*0.12;

  reactorParticles.rotation.y = motionTime * 0.025;
  reactorParticles.rotation.x = Math.sin(motionTime * 0.15) * 0.15;
  reactorParticles.scale.setScalar(1 + low * 0.05);
  particleMat.size = 0.025 + high * 0.012;

  if (!disabled) drawMatrix();
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

// READY from a command/mic callback must not overwrite ongoing speech.
let speechState = "READY";
function setActivity(state) {
  if (state === "READY" && speechState !== "READY") state = speechState;
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
const speech = new SpeechPlayer({
  fetchAudio: async (text, { signal }) => {
    const response = await fetch(`${API_BASE}/api/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: "jenny" }),
      signal,
    });
    if (!response.ok) throw new Error(`TTS API error: ${response.status}`);
    return response.json();
  },
  onState: (state) => {
    speechState = state;
    setActivity(state);
  },
});

function speak(text) {
  return speech.speak(text);
}

function stopSpeaking() {
  speech.stop();
}

window.addEventListener("pagehide", () => speech.destroy());

// Mute/unmute toggle
const muteButton = document.getElementById("mute");
if (muteButton) {
  muteButton.addEventListener("click", () => {
    speechEnabled = !speechEnabled;
    speech.setEnabled(speechEnabled);
    if (speechEnabled) speech.unlock();
    
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
  stopSpeaking();
  speech.unlock(); // user gesture: unlock Web Audio before awaiting the model

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
    stopSpeaking();
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
      speech.unlock();
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
