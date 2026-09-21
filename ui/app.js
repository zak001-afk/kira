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
// KIRA CINEMATIC NEURAL REACTOR
// ============================================================

const reactor = new THREE.Group();
scene.add(reactor);
reactor.scale.setScalar(1.05);

// OUTER DARK METALLIC SHELL
const shellGeometry = new THREE.SphereGeometry(2.25, 96, 96);
const shellMaterial = new THREE.MeshStandardMaterial({
  color: 0x050505,
  metalness: 0.95,
  roughness: 0.28,
  emissive: 0x180000,
  emissiveIntensity: 0.18,
  transparent: true,
  opacity: 0.22,
  depthWrite: false,
});
const shell = new THREE.Mesh(shellGeometry, shellMaterial);
reactor.add(shell);

// RED HOLOGRAPHIC WIRE SHELL
const wireGeometry = new THREE.SphereGeometry(2.29, 48, 48);
const wireMaterial = new THREE.MeshBasicMaterial({
  color: 0xff1515,
  wireframe: true,
  transparent: true,
  opacity: 0.035,
});
const wireShell = new THREE.Mesh(wireGeometry, wireMaterial);
reactor.add(wireShell);

// SEGMENTED REACTOR ARMOR
const armorGroup = new THREE.Group();
reactor.add(armorGroup);

const armorMaterial = new THREE.MeshStandardMaterial({
  color: 0x090909,
  metalness: 1.0,
  roughness: 0.18,
  emissive: 0x250000,
  emissiveIntensity: 0.45,
});

const armorEdgeMaterial = new THREE.MeshBasicMaterial({
  color: 0xff1515,
  transparent: true,
  opacity: 0.55,
});

for (let i = 0; i < 12; i++) {
  const angle = (i / 12) * Math.PI * 2;
  const plateGeometry = new THREE.BoxGeometry(0.95, 0.12, 0.38);
  const plate = new THREE.Mesh(plateGeometry, armorMaterial);
  plate.position.set(Math.cos(angle) * 1.72, Math.sin(angle) * 1.72, 0);
  plate.rotation.z = angle;
  armorGroup.add(plate);

  const edgeGeometry = new THREE.BoxGeometry(0.98, 0.025, 0.4);
  const edge = new THREE.Mesh(edgeGeometry, armorEdgeMaterial);
  edge.position.copy(plate.position);
  edge.rotation.copy(plate.rotation);
  edge.position.z += 0.24;
  armorGroup.add(edge);
}

const verticalArmor = new THREE.Group();
reactor.add(verticalArmor);

for (let i = 0; i < 8; i++) {
  const angle = (i / 8) * Math.PI * 2;
  const plateGeometry = new THREE.BoxGeometry(0.32, 1.15, 0.1);
  const plate = new THREE.Mesh(plateGeometry, armorMaterial);
  plate.position.set(Math.cos(angle) * 1.95, 0, Math.sin(angle) * 1.95);
  plate.rotation.y = -angle;
  verticalArmor.add(plate);
}

// INNER ENERGY SPHERE
const energyGeometry = new THREE.SphereGeometry(1.55, 64, 64);
const energyMaterial = new THREE.MeshBasicMaterial({
  color: 0xff0808,
  transparent: true,
  opacity: 0.2,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});
const energySphere = new THREE.Mesh(energyGeometry, energyMaterial);
reactor.add(energySphere);

// CORE
const coreGeometry = new THREE.SphereGeometry(0.42, 64, 64);
const coreMaterial = new THREE.MeshBasicMaterial({
  color: 0xffffff,
  toneMapped: false,
});
const core = new THREE.Mesh(coreGeometry, coreMaterial);
reactor.add(core);

// CORE RED GLOW
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

// WHITE HOT CORE AURA
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

// CENTRAL NEURAL PROCESSOR
const neuralCore = new THREE.Group();
reactor.add(neuralCore);

const innerRingGeometry = new THREE.TorusGeometry(0.62, 0.035, 12, 96);
const innerRingMaterial = new THREE.MeshBasicMaterial({
  color: 0xff2020,
  transparent: true,
  opacity: 0.9,
  blending: THREE.AdditiveBlending,
});
const innerRing = new THREE.Mesh(innerRingGeometry, innerRingMaterial);
innerRing.rotation.x = Math.PI / 2;
neuralCore.add(innerRing);

const secondRingGeometry = new THREE.TorusGeometry(0.92, 0.018, 12, 128);
const secondRingMaterial = new THREE.MeshBasicMaterial({
  color: 0xff3030,
  transparent: true,
  opacity: 0.65,
  blending: THREE.AdditiveBlending,
});
const secondRing = new THREE.Mesh(secondRingGeometry, secondRingMaterial);
secondRing.rotation.x = Math.PI / 2;
neuralCore.add(secondRing);

const frameGeometry = new THREE.CylinderGeometry(0.48, 0.48, 0.16, 32);
const frameMaterial = new THREE.MeshStandardMaterial({
  color: 0x090909,
  metalness: 1,
  roughness: 0.2,
  emissive: 0x220000,
  emissiveIntensity: 0.3,
});
const coreFrame = new THREE.Mesh(frameGeometry, frameMaterial);
coreFrame.rotation.x = Math.PI / 2;
neuralCore.add(coreFrame);

const discGeometry = new THREE.CylinderGeometry(0.34, 0.34, 0.18, 64);
const discMaterial = new THREE.MeshBasicMaterial({
  color: 0xff0808,
  transparent: true,
  opacity: 1.0,
  blending: THREE.AdditiveBlending,
});
const energyDisc = new THREE.Mesh(discGeometry, discMaterial);
energyDisc.rotation.x = Math.PI / 2;
energyDisc.position.z = 0.11;
neuralCore.add(energyDisc);

// ROTATING NEURAL RINGS
const neuralOrbit1 = new THREE.Group();
const neuralOrbit2 = new THREE.Group();
neuralCore.add(neuralOrbit1);
neuralCore.add(neuralOrbit2);

const neuralOrbitGeometry = new THREE.TorusGeometry(1.15, 0.012, 8, 128);
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

// NEURAL ENERGY BEAMS
const beamGroup = new THREE.Group();
reactor.add(beamGroup);

const beamMaterial = new THREE.MeshBasicMaterial({
  color: 0xff2020,
  transparent: true,
  opacity: 0.45,
  blending: THREE.AdditiveBlending,
});

for (let i = 0; i < 8; i++) {
  const angle = (i / 8) * Math.PI * 2;
  const beamGeometry = new THREE.BoxGeometry(0.025, 1.7, 0.025);
  const beam = new THREE.Mesh(beamGeometry, beamMaterial);
  beam.position.set(Math.cos(angle) * 0.95, Math.sin(angle) * 0.95, 0);
  beam.rotation.z = angle;
  beamGroup.add(beam);
}

// ENERGY HALO
const haloGeometry = new THREE.RingGeometry(0.62, 0.82, 96);
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

// POINT LIGHT
const reactorLight = new THREE.PointLight(0xff1010, 11, 8);
reactorLight.position.set(0, 0, 0);
reactor.add(reactorLight);

// ORBITAL RINGS
const ringMaterials = [];

function createReactorRing(radius, tube, rotation, opacity) {
  const geometry = new THREE.TorusGeometry(radius, tube, 12, 180);
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

const ring1 = createReactorRing(3.05, 0.012, new THREE.Euler(1.1, 0.15, 0.25), 0.28);
const ring2 = createReactorRing(2.75, 0.018, new THREE.Euler(0.25, 1.15, 0.5), 0.2);
const ring3 = createReactorRing(3.35, 0.009, new THREE.Euler(1.55, 0.55, 0.2), 0.14);
const ring4 = createReactorRing(2.45, 0.008, new THREE.Euler(0.4, 0.8, 1.2), 0.14);

// REACTOR ENERGY PARTICLES
const particleCount = 450;
const particlePositions = new Float32Array(particleCount * 3);
const particleSizes = new Float32Array(particleCount);

for (let i = 0; i < particleCount; i++) {
  const radius = 2.4 + Math.random() * 2.2;
  const theta = Math.random() * Math.PI * 2;
  const phi = Math.acos(2 * Math.random() - 1);
  particlePositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
  particlePositions[i * 3 + 1] = radius * Math.cos(phi);
  particlePositions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
  particleSizes[i] = 0.02 + Math.random() * 0.045;
}

const particleGeometry = new THREE.BufferGeometry();
particleGeometry.setAttribute("position", new THREE.BufferAttribute(particlePositions, 3));

const particleMaterial = new THREE.PointsMaterial({
  color: 0xff2020,
  size: 0.025,
  transparent: true,
  opacity: 0.38,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});

const reactorParticles = new THREE.Points(particleGeometry, particleMaterial);
reactor.add(reactorParticles);

/* =========================================================
   MATRIX
   ========================================================= */

const matrixCanvas = document.getElementById("matrix");
const matrixContext = matrixCanvas.getContext("2d");
let matrixWidth = 0;
let matrixHeight = 0;
let matrixColumns = [];
const matrixFontSize = 12;

function resizeMatrix() {
  matrixWidth = matrixCanvas.width = window.innerWidth;
  matrixHeight = matrixCanvas.height = window.innerHeight;
  const columns = Math.floor(matrixWidth / matrixFontSize);
  matrixColumns = new Array(columns)
    .fill(0)
    .map(() => (Math.random() * matrixHeight) / matrixFontSize);
}

function drawMatrix() {
  matrixContext.fillStyle = "rgba(0, 0, 0, 0.075)";
  matrixContext.fillRect(0, 0, matrixWidth, matrixHeight);
  matrixContext.font = `${matrixFontSize}px Consolas`;

  for (let i = 0; i < matrixColumns.length; i++) {
    const char = Math.random() > 0.5 ? "1" : "0";
    const x = i * matrixFontSize;
    const y = matrixColumns[i] * matrixFontSize;
    const brightness = Math.random();

    if (brightness > 0.85) {
      matrixContext.fillStyle = "#ff5555";
    } else if (brightness > 0.45) {
      matrixContext.fillStyle = "#d51b1b";
    } else {
      matrixContext.fillStyle = "#8b1010";
    }

    matrixContext.fillText(char, x, y);

    if (y > matrixHeight && Math.random() > 0.975) {
      matrixColumns[i] = 0;
    } else {
      matrixColumns[i] += 0.75;
    }
  }
}

/* =========================================================
   ANIMATION
   ========================================================= */

const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  const time = performance.now() * 0.001;

  reactor.rotation.y = time * 0.12;
  reactor.rotation.x = Math.sin(time * 0.18) * 0.08;
  armorGroup.rotation.y = -time * 0.08;
  verticalArmor.rotation.y = time * 0.05;
  halo.rotation.z = time * 1.8;
  neuralCore.rotation.z = time * 0.35;
  innerRing.rotation.z = time * 1.2;
  secondRing.rotation.z = -time * 0.8;
  neuralOrbit1.rotation.x = time * 0.7;
  neuralOrbit1.rotation.y = time * 0.4;
  neuralOrbit2.rotation.x = -time * 0.5;
  neuralOrbit2.rotation.z = time * 0.8;
  energyDisc.scale.setScalar(1 + Math.sin(time * 4) * 0.08);
  beamGroup.rotation.z = -time * 0.25;

  ring1.rotation.z += 0.0025;
  ring1.rotation.x += 0.001;
  ring2.rotation.y += 0.003;
  ring2.rotation.z -= 0.0012;
  ring3.rotation.x -= 0.0015;
  ring3.rotation.y += 0.0018;
  ring4.rotation.z += 0.0035;

  const energyPulse = 1 + Math.sin(time * 2.8) * 0.055;
  energySphere.scale.setScalar(energyPulse);

  const corePulse = 1 + Math.sin(time * 4.5) * 0.12;
  core.scale.setScalar(corePulse);

  const glowPulse = 1 + Math.sin(time * 3.2) * 0.16;
  coreGlow.scale.setScalar(glowPulse);

  const whitePulse = 1 + Math.sin(time * 4.5) * 0.1;
  whiteGlow.scale.setScalar(whitePulse);
  whiteGlowMaterial.opacity = 0.22 + Math.sin(time * 4.5) * 0.06;

  reactorLight.intensity = 9 + Math.sin(time * 4.5) * 3;

  reactorParticles.rotation.y = time * 0.025;
  reactorParticles.rotation.x = Math.sin(time * 0.15) * 0.15;

  drawMatrix();
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
const API_BASE = window.location.origin;

// Set boot time
document.getElementById("boot-time").textContent = new Date().toTimeString().slice(0, 5);

// Conversation management
function addMessage(sender, text, isUser = false) {
  const conversation = document.getElementById("conversation");
  const time = new Date().toTimeString().slice(0, 5);
  
  const block = document.createElement("div");
  block.className = "message-block";
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
  } else if (state !== "STANDBY") {
    dotEl.classList.add("active");
  }
}

// Send command to backend (works in both native and browser modes)
async function sendCommand(text) {
  if (!text.trim()) return;
  
  addMessage("YOU", text, true);
  setActivity("THINKING");
  
  try {
    let data;
    
    if (IS_NATIVE && window.pywebview && window.pywebview.api) {
      // Native app mode: use pywebview bridge
      data = await window.pywebview.api.send_command(text);
    } else {
      // Browser mode: use HTTP API
      const response = await fetch(`${API_BASE}/api/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      data = await response.json();
    }
    
    if (data.response) {
      addMessage("KIRA", data.response);
    } else if (data.action && data.success) {
      addMessage("KIRA", `Action completed: ${data.action}`);
    } else if (data.error) {
      addMessage("SYSTEM", `Error: ${data.error}`);
    }
    
    setActivity("READY");
  } catch (error) {
    addMessage("SYSTEM", "Failed to connect to KIRA backend");
    setActivity("ERROR");
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
    }
    if (data.memory_percent !== undefined) {
      document.getElementById("memory").textContent = `${data.memory_percent}%`;
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
