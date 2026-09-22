import * as THREE from "three";
import { SpeechPlayer } from "./speech.mjs";
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

// --- INNER ENERGY SPHERE ---
const energyGeometry = new THREE.SphereGeometry(1.55, 64, 64);
const energyMaterial = new THREE.MeshBasicMaterial({
  color: 0xff0808,
  transparent: true,
  opacity: 0.2,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});
// Deform on the GPU: the voice gives the energy shell a soft, living surface.
// Reuse uniforms/buffers each frame; no per-frame geometry reconstruction.
const voiceUniforms = {
  voiceTime: { value: 0 },
  voiceEnergy: { value: 0 },
  voiceLow: { value: 0 },
  voiceHigh: { value: 0 },
};
energyMaterial.onBeforeCompile = (shader) => {
  Object.assign(shader.uniforms, voiceUniforms);
  shader.vertexShader = `
    uniform float voiceTime;
    uniform float voiceEnergy;
    uniform float voiceLow;
    uniform float voiceHigh;
  ` + shader.vertexShader;
  shader.vertexShader = shader.vertexShader.replace("#include <begin_vertex>", `
    #include <begin_vertex>
    float wave = sin(position.y * 5.0 + voiceTime * 3.0)
               * cos(position.x * 4.0 - voiceTime * 2.0);
    float detail = sin(position.z * 9.0 + voiceTime * 5.0);
    transformed += normal * (wave * (voiceEnergy * 0.12 + voiceLow * 0.16)
                           + detail * voiceHigh * 0.06);
  `);
};
const energySphere = new THREE.Mesh(energyGeometry, energyMaterial);
reactor.add(energySphere);

// --- CORE ---
const coreGeometry = new THREE.SphereGeometry(0.42, 64, 64);
const coreMaterial = new THREE.MeshBasicMaterial({
  color: 0xffffff,
  toneMapped: false,
});
const core = new THREE.Mesh(coreGeometry, coreMaterial);
reactor.add(core);

// --- CORE GLOW ---
const glowGeometry = new THREE.SphereGeometry(0.78, 64, 64);
const glowMaterial = new THREE.MeshBasicMaterial({
  color: 0xff1515,
  transparent: true,
  opacity: 0.42,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
  toneMapped: false,
});
const coreGlow = new THREE.Mesh(glowGeometry, glowMaterial);
reactor.add(coreGlow);

// --- WHITE HOT AURA ---
const whiteGlowGeometry = new THREE.SphereGeometry(0.62, 64, 64);
const whiteGlowMaterial = new THREE.MeshBasicMaterial({
  color: 0xffdddd,
  transparent: true,
  opacity: 0.28,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
  toneMapped: false,
});
const whiteGlow = new THREE.Mesh(whiteGlowGeometry, whiteGlowMaterial);
reactor.add(whiteGlow);

// --- NEURAL CORE (central processor) ---
const neuralCore = new THREE.Group();
reactor.add(neuralCore);

const innerRingGeo = new THREE.TorusGeometry(0.62, 0.035, 12, 96);
const innerRingMat = new THREE.MeshBasicMaterial({
  color: 0xff2020,
  transparent: true,
  opacity: 0.9,
  blending: THREE.AdditiveBlending,
});
const innerRing = new THREE.Mesh(innerRingGeo, innerRingMat);
innerRing.rotation.x = Math.PI / 2;
neuralCore.add(innerRing);

const secondRingGeo = new THREE.TorusGeometry(0.92, 0.018, 12, 128);
const secondRingMat = new THREE.MeshBasicMaterial({
  color: 0xff3030,
  transparent: true,
  opacity: 0.65,
  blending: THREE.AdditiveBlending,
});
const secondRing = new THREE.Mesh(secondRingGeo, secondRingMat);
secondRing.rotation.x = Math.PI / 2;
neuralCore.add(secondRing);

const frameGeo = new THREE.CylinderGeometry(0.48, 0.48, 0.16, 32);
const frameMat = new THREE.MeshStandardMaterial({
  color: 0x090909,
  metalness: 1,
  roughness: 0.2,
  emissive: 0x220000,
  emissiveIntensity: 0.3,
});
const coreFrame = new THREE.Mesh(frameGeo, frameMat);
coreFrame.rotation.x = Math.PI / 2;
neuralCore.add(coreFrame);

const discGeo = new THREE.CylinderGeometry(0.34, 0.34, 0.18, 64);
const discMat = new THREE.MeshBasicMaterial({
  color: 0xff0808,
  transparent: true,
  opacity: 1.0,
  blending: THREE.AdditiveBlending,
});
const energyDisc = new THREE.Mesh(discGeo, discMat);
energyDisc.rotation.x = Math.PI / 2;
energyDisc.position.z = 0.11;
neuralCore.add(energyDisc);

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
let lastFrame = performance.now();
let voiceRotation = 0;

function animate() {
  requestAnimationFrame(animate);
  const now = performance.now();
  const time = now * 0.001;
  const dt = Math.min((now - lastFrame) / 1000, 0.1);
  lastFrame = now;
  const voice = speech.motion.sample(now);
  // Reduced motion keeps a quiet brightness cue, not speech-driven movement.
  const energy = reducedMotion.matches ? 0 : voice.energy;
  const low = reducedMotion.matches ? 0 : voice.low;
  const high = reducedMotion.matches ? 0 : voice.high;
  const light = voice.energy * (reducedMotion.matches ? 0.12 : 1);
  const motionTime = reducedMotion.matches ? 0 : time;
  const step = reducedMotion.matches ? 0 : dt;
  voiceRotation += energy * step;
  voiceUniforms.voiceTime.value = motionTime;
  voiceUniforms.voiceEnergy.value = energy;
  voiceUniforms.voiceLow.value = low;
  voiceUniforms.voiceHigh.value = high;

  // Keep the original silhouette. Vowels expand the core; crisp consonants
  // brighten the inner rings. Silence releases smoothly to its idle breath.
  reactor.rotation.y = motionTime * 0.12;
  reactor.rotation.x = Math.sin(motionTime * 0.18) * 0.08;
  reactor.position.y = Math.sin(motionTime * 3.5) * energy * 0.06;
  armorGroup.rotation.y = -motionTime * 0.08;
  verticalArmor.rotation.y = motionTime * 0.05;
  halo.rotation.z = motionTime * 1.8 + voiceRotation * 0.5;
  halo.scale.setScalar(1 + low * 0.25);
  haloMat.opacity = 0.35 + light * 0.12;
  neuralCore.rotation.z = motionTime * 0.35 + voiceRotation * 0.65;
  neuralCore.scale.setScalar(1 + energy * 0.1);
  innerRing.rotation.z = motionTime * 1.2 + voiceRotation;
  innerRing.scale.setScalar(1 + high * 0.25);
  secondRing.rotation.z = -motionTime * 0.8 - voiceRotation * 0.7;
  secondRing.scale.setScalar(1 + low * 0.2);
  neuralOrbit1.rotation.x = motionTime * 0.7 + voiceRotation;
  neuralOrbit1.rotation.y = motionTime * 0.4;
  neuralOrbit2.rotation.x = -motionTime * 0.5;
  neuralOrbit2.rotation.z = motionTime * 0.8 + voiceRotation;
  energyDisc.scale.setScalar(1 + Math.sin(motionTime * 4) * 0.04 + energy * 0.2);
  beamGroup.rotation.z = -motionTime * 0.25;
  beamGroup.scale.setScalar(1 + low * 0.12);
  beamMat.opacity = 0.45 + light * 0.14;

  // Frame-rate independent ring movement.
  ring1.rotation.z += step * 0.15;
  ring1.rotation.x += step * 0.06;
  ring2.rotation.y += step * 0.18;
  ring2.rotation.z -= step * 0.072;
  ring3.rotation.x -= step * 0.09;
  ring3.rotation.y += step * 0.108;
  ring4.rotation.z += step * 0.21;

  energySphere.scale.setScalar(1 + Math.sin(motionTime * 2.8) * 0.03 + energy * 0.1 + low * 0.08);
  const breath = Math.sin(motionTime * 2.2) * 0.035;
  core.scale.set(1 + breath + energy * 0.16, 1 + breath + energy * 0.34, 1 + breath + low * 0.2);
  coreGlow.scale.setScalar(1 + breath + energy * 0.28);
  glowMaterial.opacity = 0.38 + light * 0.12;
  whiteGlow.scale.setScalar(1 + breath + high * 0.22 + energy * 0.1);
  whiteGlowMaterial.opacity = 0.22 + light * 0.07;
  reactorLight.intensity = 9 + light * 3;
  bloomPass.strength = 1.45 + light * 0.18;

  reactorParticles.rotation.y = motionTime * 0.025;
  reactorParticles.rotation.x = Math.sin(motionTime * 0.15) * 0.15;
  reactorParticles.scale.setScalar(1 + low * 0.05);
  particleMat.size = 0.025 + high * 0.012;

  if (!reducedMotion.matches) drawMatrix();
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
