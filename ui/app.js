import * as THREE from "three";
import { SpeechPlayer } from "./speech.mjs?v=speech-sync-2";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

/* =========================================================
   KIRA // AI COMMAND CENTER — thème or
   ========================================================= */

const GOLD = 0xC2A66B;
const GOLD_BRIGHT = 0xE3D3A6;
const GOLD_SOFT = 0xD5BE8A;
const GOLD_DARK = 0x5C4A28;
const GOLD_DEEP = 0x241C0F;

/* =========================================================
   SCÈNE
   ========================================================= */

const container = document.getElementById("scene-container");
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x030200);

/* =========================================================
   CAMÉRA
   ========================================================= */

const camera = new THREE.PerspectiveCamera(
  45,
  window.innerWidth / window.innerHeight,
  0.1,
  1000
);
camera.position.set(0, 0, 15);

/* =========================================================
   RENDU
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
   LUMIÈRES
   ========================================================= */

const ambient = new THREE.AmbientLight(0x1a1206, 2);
scene.add(ambient);

const goldLight = new THREE.PointLight(GOLD, 16, 14);
goldLight.position.set(0, 1, 4);
scene.add(goldLight);

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
bloomPass.strength = 1.4;
bloomPass.radius = 0.7;
composer.addPass(bloomPass);

/* =========================================================
   RÉACTEUR — machinery orbitale dorée
   ========================================================= */

const reactor = new THREE.Group();
scene.add(reactor);
reactor.scale.setScalar(1.05);

// --- COQUILLE EXTERNE ---
const shellGeometry = new THREE.SphereGeometry(2.25, 64, 64);
const shellMaterial = new THREE.MeshStandardMaterial({
  color: 0x0a0703,
  metalness: 0.95,
  roughness: 0.25,
  emissive: 0x241C0F,
  emissiveIntensity: 0.18,
  transparent: true,
  opacity: 0.16,
  depthWrite: false,
});
const shell = new THREE.Mesh(shellGeometry, shellMaterial);
// reactor.add(shell); // retiré : centre vide

// --- COQUILLE FILAIRE ---
const wireGeometry = new THREE.SphereGeometry(2.3, 32, 32);
const wireMaterial = new THREE.MeshBasicMaterial({
  color: 0xA08652,
  wireframe: true,
  transparent: true,
  opacity: 0.03,
});
const wireShell = new THREE.Mesh(wireGeometry, wireMaterial);
// reactor.add(wireShell); // retiré : centre vide

// --- ANNEAUX DE BLINDAGE (plaques orbitales) ---
const armorGroup = new THREE.Group();
// reactor.add(armorGroup); // retiré : centre vide

const armorMaterial = new THREE.MeshStandardMaterial({
  color: 0x120c04,
  metalness: 1.0,
  roughness: 0.18,
  emissive: 0x6E5A33,
  emissiveIntensity: 0.4,
});

for (let i = 0; i < 12; i++) {
  const angle = (i / 12) * Math.PI * 2;
  const plateGeo = new THREE.BoxGeometry(1.35, 0.1, 0.32);
  const plate = new THREE.Mesh(plateGeo, armorMaterial);
  plate.position.set(Math.cos(angle) * 4.3, Math.sin(angle) * 4.3, 0);
  plate.rotation.z = angle;
  armorGroup.add(plate);
}

// --- BLINDAGE VERTICAL ---
const verticalArmor = new THREE.Group();
// reactor.add(verticalArmor); // retiré : centre vide

for (let i = 0; i < 8; i++) {
  const angle = (i / 8) * Math.PI * 2;
  const plateGeo = new THREE.BoxGeometry(0.34, 1.5, 0.09);
  const plate = new THREE.Mesh(plateGeo, armorMaterial);
  plate.position.set(Math.cos(angle) * 4.9, 0, Math.sin(angle) * 4.9);
  plate.rotation.y = -angle;
  verticalArmor.add(plate);
}

// --- AURA D'ÉNERGIE (derrière l'avatar, se déforme avec la voix) ---
const energyGeometry = new THREE.SphereGeometry(2.6, 64, 64);
const energyMaterial = new THREE.MeshBasicMaterial({
  color: 0xC2A66B,
  transparent: true,
  opacity: 0.1,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});
// Déformation GPU : la voix donne à l'aura une surface vivante.
// Uniforms réutilisés à chaque frame ; aucune reconstruction de géométrie.
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
energySphere.position.z = -3.2;
// reactor.add(energySphere); // retiré : centre vide

/* =========================================================
   AVATAR — visage doré de KIRA
   ========================================================= */

const avatarGroup = new THREE.Group();
// Avatar désactivé : centre volontairement vide.
if (false) scene.add(avatarGroup);

if (THREE.TextureLoader && THREE.PlaneGeometry) {
  const avatarLoader = new THREE.TextureLoader();
  const avatarTexture = avatarLoader.load("assets/avatar_gold.png", (texture) => {
    if (texture && THREE.SRGBColorSpace) texture.colorSpace = THREE.SRGBColorSpace;
    if (texture) texture.needsUpdate = true;
  });
  // Rendu "visage réel" : blending normal (peau opaque, tons naturels).
  // depthTest désactivé + renderOrder maximal : le visage est TOUJOURS
  // dessiné en dernier, au-dessus de toute la machinerie — aucun élément 3D
  // ne peut jamais passer devant, quelle que soit sa position.
  const avatarMaterial = new THREE.MeshBasicMaterial({
    map: avatarTexture,
    transparent: true,
    opacity: 1.0,
    depthWrite: false,
    depthTest: false,
    toneMapped: false,
  });
  const avatarPlane = new THREE.Mesh(
    new THREE.PlaneGeometry(6.4, 6.4),
    avatarMaterial
  );
  avatarPlane.renderOrder = 50;
  avatarPlane.position.set(0, 0.4, 5.2);
  avatarGroup.add(avatarPlane);
}

/* =========================================================
   CLUSTER DU CŒUR — nœud d'énergie (fixe, sur la poitrine)
   ========================================================= */

const coreCluster = new THREE.Group();
coreCluster.position.set(0, -4.1, 0.4);
// Noyau désactivé : centre volontairement vide.
if (false) scene.add(coreCluster);

// --- CŒUR ---
const coreGeometry = new THREE.SphereGeometry(0.42, 64, 64);
const coreMaterial = new THREE.MeshBasicMaterial({
  color: 0xfff6df,
  toneMapped: false,
});
const core = new THREE.Mesh(coreGeometry, coreMaterial);
coreCluster.add(core);

// --- HALO DU CŒUR ---
const glowGeometry = new THREE.SphereGeometry(0.78, 64, 64);
const glowMaterial = new THREE.MeshBasicMaterial({
  color: 0xC2A66B,
  transparent: true,
  opacity: 0.42,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
  toneMapped: false,
});
const coreGlow = new THREE.Mesh(glowGeometry, glowMaterial);
coreCluster.add(coreGlow);

// --- AURA BLANCHE CHAUDE ---
const whiteGlowGeometry = new THREE.SphereGeometry(0.62, 64, 64);
const whiteGlowMaterial = new THREE.MeshBasicMaterial({
  color: 0xffefd0,
  transparent: true,
  opacity: 0.28,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
  toneMapped: false,
});
const whiteGlow = new THREE.Mesh(whiteGlowGeometry, whiteGlowMaterial);
coreCluster.add(whiteGlow);

// --- NOYAU NEURAL (anneaux concentriques) ---
const neuralCore = new THREE.Group();
coreCluster.add(neuralCore);

const innerRingGeo = new THREE.TorusGeometry(0.62, 0.035, 12, 96);
const innerRingMat = new THREE.MeshBasicMaterial({
  color: GOLD,
  transparent: true,
  opacity: 0.9,
  blending: THREE.AdditiveBlending,
});
const innerRing = new THREE.Mesh(innerRingGeo, innerRingMat);
innerRing.rotation.x = Math.PI / 2;
neuralCore.add(innerRing);

const secondRingGeo = new THREE.TorusGeometry(0.92, 0.018, 12, 128);
const secondRingMat = new THREE.MeshBasicMaterial({
  color: GOLD_BRIGHT,
  transparent: true,
  opacity: 0.65,
  blending: THREE.AdditiveBlending,
});
const secondRing = new THREE.Mesh(secondRingGeo, secondRingMat);
secondRing.rotation.x = Math.PI / 2;
neuralCore.add(secondRing);

const frameGeo = new THREE.CylinderGeometry(0.48, 0.48, 0.16, 32);
const frameMat = new THREE.MeshStandardMaterial({
  color: 0x120c04,
  metalness: 1,
  roughness: 0.2,
  emissive: 0x6E5A33,
  emissiveIntensity: 0.3,
});
const coreFrame = new THREE.Mesh(frameGeo, frameMat);
coreFrame.rotation.x = Math.PI / 2;
neuralCore.add(coreFrame);

const discGeo = new THREE.CylinderGeometry(0.34, 0.34, 0.18, 64);
const discMat = new THREE.MeshBasicMaterial({
  color: 0xC2A66B,
  transparent: true,
  opacity: 1.0,
  blending: THREE.AdditiveBlending,
});
const energyDisc = new THREE.Mesh(discGeo, discMat);
energyDisc.rotation.x = Math.PI / 2;
energyDisc.position.z = 0.11;
neuralCore.add(energyDisc);

// --- ORBITES NEURALES ---
const neuralOrbit1 = new THREE.Group();
const neuralOrbit2 = new THREE.Group();
neuralCore.add(neuralOrbit1);
neuralCore.add(neuralOrbit2);

const orbitGeo = new THREE.TorusGeometry(1.15, 0.012, 8, 128);
const orbitMat = new THREE.MeshBasicMaterial({
  color: GOLD,
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

// --- FAISCEAUX D'ÉNERGIE ---
const beamGroup = new THREE.Group();
// reactor.add(beamGroup); // retiré : centre vide

const beamMat = new THREE.MeshBasicMaterial({
  color: GOLD,
  transparent: true,
  opacity: 0.4,
  blending: THREE.AdditiveBlending,
});

for (let i = 0; i < 8; i++) {
  const angle = (i / 8) * Math.PI * 2;
  const beamGeo = new THREE.BoxGeometry(0.025, 1.6, 0.025);
  const beam = new THREE.Mesh(beamGeo, beamMat);
  beam.position.set(Math.cos(angle) * 3.6, Math.sin(angle) * 3.6, 0);
  beam.rotation.z = angle;
  beamGroup.add(beam);
}

// --- HALO ---
const haloGeo = new THREE.RingGeometry(3.1, 3.35, 96);
const haloMat = new THREE.MeshBasicMaterial({
  color: GOLD,
  transparent: true,
  opacity: 0.3,
  side: THREE.DoubleSide,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});
const halo = new THREE.Mesh(haloGeo, haloMat);
halo.rotation.x = Math.PI / 2;
// reactor.add(halo); // retiré : centre vide

// --- LUMIÈRE DU RÉACTEUR ---
const reactorLight = new THREE.PointLight(0xC2A66B, 3, 9);
reactorLight.position.set(0, -4.1, 1.0);
scene.add(reactorLight);

// --- ANNEAUX ORBITAUX ---
function createReactorRing(radius, tube, rotation, opacity) {
  const geo = new THREE.TorusGeometry(radius, tube, 12, 180);
  const mat = new THREE.MeshBasicMaterial({
    color: 0xC2A66B,
    transparent: true,
    opacity: opacity,
  });
  const ring = new THREE.Mesh(geo, mat);
  ring.rotation.set(rotation.x, rotation.y, rotation.z);
  reactor.add(ring);
  return ring;
}

const ring1 = createReactorRing(3.05, 0.012, new THREE.Euler(1.25, 0.15, 0.25), 0.3);
const ring2 = createReactorRing(2.75, 0.018, new THREE.Euler(0.35, 1.15, 0.5), 0.22);
const ring3 = createReactorRing(3.35, 0.009, new THREE.Euler(1.55, 0.55, 0.2), 0.16);
const ring4 = createReactorRing(2.45, 0.008, new THREE.Euler(0.4, 0.8, 1.2), 0.15);

// --- PARTICULES D'OR ---
const particleCount = 520;
const particlePositions = new Float32Array(particleCount * 3);

for (let i = 0; i < particleCount; i++) {
  const radius = 2.6 + Math.random() * 2.4;
  const theta = Math.random() * Math.PI * 2;
  const phi = Math.acos(2 * Math.random() - 1);
  particlePositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
  particlePositions[i * 3 + 1] = radius * Math.cos(phi);
  particlePositions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
}

const particleGeo = new THREE.BufferGeometry();
particleGeo.setAttribute("position", new THREE.BufferAttribute(particlePositions, 3));

const particleMat = new THREE.PointsMaterial({
  color: GOLD,
  size: 0.028,
  transparent: true,
  opacity: 0.4,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});

const reactorParticles = new THREE.Points(particleGeo, particleMat);
reactor.add(reactorParticles);

/* =========================================================
   REDIMENSIONNEMENT
   ========================================================= */

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  composer.setSize(window.innerWidth, window.innerHeight);
});

/* =========================================================
   INTÉGRATION BACKEND KIRA
   ========================================================= */

// Détection pywebview (app native) ou navigateur.
// window.KIRA_API_BASE permet de servir l'UI derrière un proxy même origine.
const IS_NATIVE = typeof window.pywebview !== "undefined";
const API_BASE = window.KIRA_API_BASE
  || "";

// Heure de session
const bootTimeEl = document.getElementById("boot-time");
if (bootTimeEl) bootTimeEl.textContent = new Date().toTimeString().slice(0, 5);

// ─────────────────────────────────────────────
// Horloge
// ─────────────────────────────────────────────

function updateClock() {
  const now = new Date();
  const timeEl = document.getElementById("clock-time");
  const dateEl = document.getElementById("clock-date");

  if (timeEl) {
    timeEl.textContent = now.toLocaleTimeString("fr-FR", { hour12: false });
  }

  if (dateEl) {
    const label = now.toLocaleDateString("fr-FR", {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
    });
    dateEl.textContent = label.charAt(0).toUpperCase() + label.slice(1);
  }
}

updateClock();
setInterval(updateClock, 1000);

// ─────────────────────────────────────────────
// Conversation
// ─────────────────────────────────────────────

function escapeHtml(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function addMessage(sender, text, isUser = false, extraClass = "") {
  const conversation = document.getElementById("conversation");
  const time = new Date().toTimeString().slice(0, 5);

  const block = document.createElement("div");
  block.className = (isUser ? "message-block user-block " : "message-block ") + extraClass;
  block.innerHTML = `
    <div class="message-meta ${isUser ? "user" : ""}">${escapeHtml(sender)} &nbsp;//&nbsp; ${time}</div>
    <div class="message">${escapeHtml(text).replace(/\n/g, "<br />")}</div>
  `;

  conversation.appendChild(block);
  conversation.scrollTop = conversation.scrollHeight;
}

function addHistoryDivider() {
  const conversation = document.getElementById("conversation");
  const divider = document.createElement("div");
  divider.className = "history-divider";
  divider.textContent = "— mémoire récente —";
  conversation.appendChild(divider);
}

// READY renvoyé par une commande ne doit pas écraser la voix en cours.
let speechState = "READY";

const ACTIVITY_FR = {
  READY: "Prête",
  STANDBY: "Veille",
  THINKING: "Réflexion…",
  SPEAKING: "Je parle",
  LISTENING: "J'écoute",
  ERROR: "Erreur",
};

function setActivity(state) {
  if (state === "READY" && speechState !== "READY") state = speechState;
  const activityEl = document.getElementById("activity");
  const dotEl = document.getElementById("activity-dot");
  const frEl = document.getElementById("activity-fr");

  activityEl.textContent = state;
  dotEl.className = "activity-dot";
  frEl.textContent = ACTIVITY_FR[state] || state;

  if (state === "THINKING") {
    dotEl.classList.add("thinking");
  } else if (state === "SPEAKING") {
    dotEl.classList.add("speaking");
  } else if (state === "ERROR") {
    dotEl.classList.add("error");
  } else if (state !== "STANDBY") {
    dotEl.classList.add("active");
  }
}

// ─────────────────────────────────────────────
// Synthèse vocale (voix neuronales Edge)
// ─────────────────────────────────────────────

let speechEnabled = true;

function currentVoice() {
  try {
    return localStorage.getItem("kira.voice") || "jenny";
  } catch { return "jenny"; }
}

const speech = new SpeechPlayer({
  fetchAudio: async (text, { signal, language }) => {
    const response = await fetch(`${API_BASE}/api/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: currentVoice(), language }),
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
  const voice = currentVoice();
  const language = ["denise", "eloise", "vivienne", "henri"].includes(voice)
    ? "fr-FR" : voice === "aria_uk" ? "en-GB" : "en-US";
  return speech.speak(text, { language });
}

function stopSpeaking() {
  speech.stop();
}

window.addEventListener("pagehide", () => speech.destroy());

// Bouton muet
const muteButton = document.getElementById("mute");
if (muteButton) {
  muteButton.addEventListener("click", () => {
    speechEnabled = !speechEnabled;
    speech.setEnabled(speechEnabled);
    if (speechEnabled) speech.unlock();

    if (speechEnabled) {
      muteButton.innerHTML = `
        <svg viewBox="0 0 24 24">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
        </svg>
      `;
      muteButton.title = "Couper la voix";
      muteButton.classList.remove("off");
    } else {
      muteButton.innerHTML = `
        <svg viewBox="0 0 24 24">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
          <line x1="23" y1="9" x2="17" y2="15"></line>
          <line x1="17" y1="9" x2="23" y2="15"></line>
        </svg>
      `;
      muteButton.title = "Activer la voix";
      muteButton.classList.add("off");
    }

    if (!speechEnabled) {
      stopSpeaking();
    }

    console.log(`[KIRA] Voix ${speechEnabled ? "activée" : "coupée"}`);
  });
}

// ─────────────────────────────────────────────
// Envoi des commandes (app native et navigateur)
// ─────────────────────────────────────────────

async function sendCommand(text) {
  if (!text.trim()) return;
  stopSpeaking();
  speech.unlock(); // geste utilisateur : débloque Web Audio

  addMessage("Vous", text, true);
  setActivity("THINKING");

  try {
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
      addMessage("Système", `Erreur : ${data.error}`);
    } else if (data.response) {
      addMessage("KIRA", data.response);
      speak(data.response);
    } else if (data.action && data.success) {
      addMessage("KIRA", `C'est fait : ${data.action}`);
      speak(`C'est fait. ${data.action.replace(/_/g, " ")}`);
    } else if (data.action) {
      addMessage("KIRA", `Exécuté : ${data.action}`);
    } else {
      addMessage("KIRA", "C'est fait.");
    }

    setActivity("READY");
    updateTasks();
  } catch (error) {
    console.error("Commande échouée :", error);

    if (error.message.includes("Failed to fetch") || error.message.includes("NetworkError") || error.message.includes("fetch")) {
      addMessage("Système", "Impossible de joindre le serveur KIRA (" + API_BASE + "). Vérifiez que le backend est lancé.");
    } else {
      addMessage("Système", `Erreur : ${error.message}`);
    }

    setActivity("ERROR");
    setTimeout(() => setActivity("READY"), 3000);
  }
}

// Entrée clavier
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

// Commandes rapides (exposées pour onclick)
window.quickCmd = function(cmd) {
  commandInput.value = cmd;
  sendCommand(cmd);
  commandInput.value = "";
};

// ─────────────────────────────────────────────
// Saisie vocale (Web Speech API)
// ─────────────────────────────────────────────

const micButton = document.getElementById("mic");
const kButton = document.getElementById("k-btn");
let recognition = null;

function microLang() {
  try {
    return localStorage.getItem("kira.micro") || "fr-FR";
  } catch { return "fr-FR"; }
}

function startListening() {
  if (!recognition) return;
  speech.unlock();
  recognition.lang = microLang();
  try {
    recognition.start();
  } catch { /* déjà en écoute */ }
}

if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = microLang();

  recognition.onstart = () => {
    stopSpeaking();
    micButton.classList.add("listening");
    kButton.classList.add("listening");
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
    kButton.classList.remove("listening");
    setActivity("READY");
  };

  recognition.onerror = (event) => {
    console.error("Erreur de reconnaissance vocale :", event.error);
    micButton.classList.remove("listening");
    kButton.classList.remove("listening");
    showToast(event.error === "not-allowed" ? "Micro non autorisé" : "Micro indisponible");
    setActivity("ERROR");
    setTimeout(() => setActivity("READY"), 3000);
  };

  micButton.addEventListener("click", startListening);
  kButton.addEventListener("click", startListening);
} else {
  micButton.style.display = "none";
  kButton.addEventListener("click", () => {
    showToast("Reconnaissance vocale non disponible dans ce navigateur");
  });
}

// ─────────────────────────────────────────────
// Toast
// ─────────────────────────────────────────────

let toastTimer = null;

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}
window.showToast = showToast;

// ─────────────────────────────────────────────
// Jauges & étincelles (graphes)
// ─────────────────────────────────────────────

const RING_LENGTH = 2 * Math.PI * 26;

function setRing(el, ratio) {
  if (!el) return;
  const clamped = Math.max(0, Math.min(1, ratio));
  el.style.strokeDashoffset = (RING_LENGTH * (1 - clamped)).toFixed(1);
}

function setBar(id, ratio) {
  const bar = document.getElementById(id);
  if (bar) bar.style.width = (Math.max(0, Math.min(100, ratio)) + "%");
}

const sparkHistory = { cpu: [], ram: [], disk: [], net: [] };

function drawSpark(canvas, values) {
  if (!canvas || !values || values.length < 2) return;
  const ctx = canvas.getContext("2d");
  if (!ctx || typeof ctx.beginPath !== "function") return; // environnement de test

  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.beginPath();
  for (let i = 0; i < values.length; i++) {
    const x = (i / (values.length - 1)) * w;
    const y = h - Math.max(1, Math.min(1, values[i])) * (h - 3) - 1.5;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.strokeStyle = "rgba(194, 166, 107, 0.85)";
  ctx.lineWidth = 1.4;
  ctx.stroke();
  ctx.lineTo(w, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  ctx.fillStyle = "rgba(194, 166, 107, 0.14)";
  ctx.fill();
}

function pushSpark(key, value) {
  const history = sparkHistory[key];
  history.push(value);
  if (history.length > 36) history.shift();
  drawSpark(document.getElementById("spark-" + key), history);
}

function fmtSpeed(kbps) {
  if (kbps >= 1024) return (kbps / 1024).toFixed(1) + " Mo/s";
  return Math.round(kbps) + " ko/s";
}

let netPeak = 64; // pic de référence (ko/s), ajusté en continu
let backendOnline = false;

async function updateTelemetry() {
  try {
    let data;

    if (IS_NATIVE && window.pywebview && window.pywebview.api) {
      data = await window.pywebview.api.get_system_info();
    } else {
      const response = await fetch(`${API_BASE}/api/system`);
      data = await response.json();
    }

    if (data.error) return;

    if (data.cpu_percent !== undefined) {
      const cpu = Number(data.cpu_percent) || 0;
      document.getElementById("val-cpu").textContent = Math.round(cpu) + "%";
      setRing(document.getElementById("ring-cpu"), cpu / 100);
      setBar("bar-core", cpu);
      document.getElementById("val-core").textContent = Math.round(cpu) + "%";
      document.getElementById("sub-cpu").textContent =
        data.cpu_cores ? data.cpu_cores + " cœurs" : "—";
      pushSpark("cpu", cpu / 100);
    }

    if (data.memory_percent !== undefined) {
      const ram = Number(data.memory_percent) || 0;
      document.getElementById("val-ram").textContent = Math.round(ram) + "%";
      setRing(document.getElementById("ring-ram"), ram / 100);
      setBar("bar-mem", ram);
      document.getElementById("val-mem").textContent = Math.round(ram) + "%";
      document.getElementById("sub-ram").textContent =
        data.memory_used_gb !== undefined
          ? data.memory_used_gb + " / " + data.memory_total_gb + " Go"
          : "—";
      pushSpark("ram", ram / 100);
    }

    if (data.disk_percent !== undefined) {
      const disk = Number(data.disk_percent) || 0;
      document.getElementById("val-disk").textContent = Math.round(disk) + "%";
      setRing(document.getElementById("ring-disk"), disk / 100);
      document.getElementById("sub-disk").textContent = "Stockage";
      pushSpark("disk", disk / 100);
    }

    const down = Number(data.net_recv_kbps) || 0;
    const up = Number(data.net_sent_kbps) || 0;
    document.getElementById("val-net").textContent = fmtSpeed(down);
    document.getElementById("val-net-up").textContent = "↑ " + fmtSpeed(up);
    document.getElementById("val-net-down").textContent = "↓ " + fmtSpeed(down);
    netPeak = Math.max(netPeak, down, up, 64);
    setRing(document.getElementById("ring-net"), down / netPeak);
    setBar("bar-net", (down / netPeak) * 100);
    document.getElementById("val-net-act").textContent = fmtSpeed(down);
    pushSpark("net", Math.min(1, down / netPeak));

    backendOnline = true;
  } catch (error) {
    backendOnline = false;
    // Backend indisponible : les jauges restent en l'état.
  }
}

// ─────────────────────────────────────────────
// Tâches
// ─────────────────────────────────────────────

const TASK_TYPE_FR = {
  todo: "À faire",
  reminder: "Rappel",
  timer: "Minuteur",
  note: "Note",
};

function taskTime(task) {
  const raw = task.due_at || task.created_at;
  if (!raw) return "--:--";
  const parsed = new Date(String(raw).replace(" ", "T"));
  if (isNaN(parsed.getTime())) return "--:--";
  return parsed.toTimeString().slice(0, 5);
}

function taskRow(task) {
  return `
    <div class="task-item">
      <span class="task-time">${taskTime(task)}</span>
      <span class="task-title">${escapeHtml(task.title)}</span>
      <span class="task-type">${TASK_TYPE_FR[task.type] || task.type || "—"}</span>
    </div>
  `;
}

function renderTasks(tasks, listId, emptyLabel) {
  const list = document.getElementById(listId);
  if (!list) return;
  if (Array.isArray(tasks) && tasks.length > 0) {
    list.innerHTML = tasks.slice(0, listId === "tasks-list" ? 5 : 30).map(taskRow).join("");
  } else {
    list.innerHTML = `<div class="task-empty">${emptyLabel}</div>`;
  }
}

async function updateTasks() {
  try {
    let data;

    if (IS_NATIVE && window.pywebview && window.pywebview.api) {
      data = await window.pywebview.api.get_tasks();
    } else {
      const response = await fetch(`${API_BASE}/api/tasks?completed=false`);
      data = await response.json();
    }

    const tasks = Array.isArray(data && data.tasks) ? data.tasks : [];
    renderTasks(tasks, "tasks-list", "Aucune tâche en attente");

    const badge = document.getElementById("bell-count");
    if (badge) {
      if (tasks.length > 0) {
        badge.textContent = tasks.length > 9 ? "9+" : String(tasks.length);
        badge.classList.remove("hidden");
      } else {
        badge.classList.add("hidden");
      }
    }

    setBar("bar-tasks", Math.min(100, tasks.length * 12));
    document.getElementById("val-tasks").textContent = String(tasks.length);
  } catch (error) {
    // Backend indisponible
  }
}

// ─────────────────────────────────────────────
// Agents (modules réels + plugins)
// ─────────────────────────────────────────────

const ICONS = {
  mic: '<svg viewBox="0 0 24 24"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path></svg>',
  memory: '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg>',
  clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>',
  plugin: '<svg viewBox="0 0 24 24"><path d="M12 2v4"></path><path d="M12 18v4"></path><path d="M2 12h4"></path><path d="M18 12h4"></path><circle cx="12" cy="12" r="4"></circle></svg>',
  eye: '<svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>',
  globe: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>',
};

let pluginCount = 0;
let pluginNames = [];

const CORE_MODULES = [
  { id: "voix", name: "Voix & Commande", desc: "Commandes vocales et réponses parlées", icon: "mic", view: "parametres" },
  { id: "memoire", name: "Mémoire persistante", desc: "Conversations et faits enregistrés localement", icon: "memory", view: "historique" },
  { id: "taches", name: "Gestion de tâches", desc: "Rappels, minuteurs et notes", icon: "clock", view: "taches" },
  { id: "plugins", name: "Plugins", desc: "0 extension chargée", icon: "plugin", view: "agents" },
  { id: "vision", name: "Vision écran", desc: "Analyse d'écran via le modèle local", icon: "eye", action: "analyze screen" },
  { id: "web", name: "Recherche web", desc: "Recherche et apprentissage en ligne", icon: "globe", action: "__web" },
];

function agentRowHtml(mod, online) {
  return `
    <div class="agent-row" onclick="agentClick('${mod.id}')">
      <span class="agent-icon">${ICONS[mod.icon]}</span>
      <span class="agent-info">
        <span class="agent-name">${mod.name}</span>
        <span class="agent-desc">${mod.desc}</span>
      </span>
      <span class="agent-status ${online ? "" : "off"}">${online ? "En ligne" : "Hors ligne"}</span>
    </div>
  `;
}

function renderAgents() {
  const list = document.getElementById("agents-list");
  if (!list) return;
  list.innerHTML = CORE_MODULES.map((mod) => agentRowHtml(mod, backendOnline)).join("");
}

window.agentClick = function(id) {
  const mod = CORE_MODULES.find((m) => m.id === id);
  if (!mod) return;
  if (mod.view) openView(mod.view);
  else if (mod.action === "__web") promptWebSearch();
  else if (mod.action) window.quickCmd(mod.action);
};

async function updatePlugins() {
  try {
    const response = await fetch(`${API_BASE}/api/plugins`);
    const data = await response.json();
    const plugins = Array.isArray(data.plugins) ? data.plugins : [];
    pluginCount = plugins.length;
    pluginNames = plugins.map((p) =>
      typeof p === "string" ? p : (p.name || p.id || "plugin")
    );
    const mod = CORE_MODULES.find((m) => m.id === "plugins");
    if (mod) mod.desc = pluginCount + " extension" + (pluginCount > 1 ? "s" : "") + " chargée" + (pluginCount > 1 ? "s" : "");
    renderAgents();
  } catch (error) {
    // Backend indisponible
  }
}

// ─────────────────────────────────────────────
// Vues (overlay central)
// ─────────────────────────────────────────────

const VIEW_TITLES = {
  taches: "Tâches",
  agents: "Agents",
  fichiers: "Fichiers",
  outils: "Outils",
  parametres: "Paramètres",
  historique: "Historique",
  systeme: "Système",
};

const VIEW_IDS = ["taches", "agents", "fichiers", "outils", "parametres", "historique", "systeme"];
const NAV_IDS = ["accueil", "conversation", "agents", "fichiers", "outils", "parametres", "historique", "systeme"];
let activeView = null;

function setActiveNav(name) {
  NAV_IDS.forEach((id) => {
    const btn = document.getElementById("nav-" + id);
    if (!btn) return;
    btn.classList.remove("active");
    if (id === name) btn.classList.add("active");
  });
}

function openView(name) {
  const overlay = document.getElementById("view-overlay");
  if (!VIEW_IDS.includes(name)) { closeView(); return; }
  activeView = name;
  overlay.classList.remove("hidden");
  document.getElementById("view-title").textContent = VIEW_TITLES[name] || name;
  VIEW_IDS.forEach((id) => {
    const body = document.getElementById("view-" + id);
    if (!body) return;
    body.classList.remove("hidden");
    if (id !== name) body.classList.add("hidden");
  });
  setActiveNav(name);
  if (name === "taches") loadTasksFull();
  if (name === "agents") loadAgentsFull();
  if (name === "historique") loadHistoryFull();
  if (name === "systeme") loadSystemFull();
  if (name === "parametres") loadParamInfo();
}
window.openView = openView;

function closeView() {
  activeView = null;
  document.getElementById("view-overlay").classList.add("hidden");
  setActiveNav("accueil");
}

window.closeView = closeView;

// ─────────────────────────────────────────────
// Chargement des vues
// ─────────────────────────────────────────────

function listRow(title, sub, side) {
  return `
    <div class="list-row">
      <div class="row-main">
        <span class="row-title">${escapeHtml(title)}</span>
        ${sub ? `<span class="row-sub">${escapeHtml(sub)}</span>` : ""}
      </div>
      ${side ? `<span class="row-side">${escapeHtml(side)}</span>` : ""}
    </div>
  `;
}

async function loadTasksFull() {
  const list = document.getElementById("tasks-full");
  try {
    const response = await fetch(`${API_BASE}/api/tasks`);
    const data = await response.json();
    const tasks = Array.isArray(data.tasks) ? data.tasks : [];
    if (tasks.length === 0) {
      list.innerHTML = '<div class="task-empty">Aucune tâche enregistrée</div>';
      return;
    }
    list.innerHTML = tasks.slice(0, 30).map((task) =>
      listRow(
        task.title,
        (TASK_TYPE_FR[task.type] || task.type || "—") + (task.completed ? " · terminée" : ""),
        taskTime(task)
      )
    ).join("");
  } catch (error) {
    list.innerHTML = '<div class="task-empty">Backend indisponible</div>';
  }
}
window.loadTasksFull = loadTasksFull;

async function loadAgentsFull() {
  const list = document.getElementById("agents-full");
  const rows = CORE_MODULES.map((mod) =>
    listRow(mod.name, mod.desc, backendOnline ? "En ligne" : "Hors ligne")
  );
  let pluginRows = "";
  if (pluginNames.length > 0) {
    pluginRows = pluginNames.map((name) =>
      listRow(String(name), "Plugin utilisateur", "Chargé")
    ).join("");
  } else {
    pluginRows = '<div class="task-empty">Aucun plugin utilisateur dans plugins/</div>';
  }
  list.innerHTML = rows.join("") + pluginRows;
}
window.loadAgentsFull = loadAgentsFull;

async function loadHistoryFull() {
  const list = document.getElementById("history-full");
  try {
    const response = await fetch(`${API_BASE}/api/history?limit=40`);
    const data = await response.json();
    const messages = Array.isArray(data.messages) ? data.messages : [];
    if (messages.length === 0) {
      list.innerHTML = '<div class="task-empty">Aucun échange enregistré</div>';
      return;
    }
    list.innerHTML = messages.map((message) =>
      listRow(
        message.content,
        message.role === "user" ? "Vous" : "KIRA",
        ""
      )
    ).join("");
  } catch (error) {
    list.innerHTML = '<div class="task-empty">Backend indisponible</div>';
  }
}
window.loadHistoryFull = loadHistoryFull;

async function loadSystemFull() {
  const list = document.getElementById("system-full");
  try {
    const [systemResponse, statusResponse] = await Promise.all([
      fetch(`${API_BASE}/api/system`),
      fetch(`${API_BASE}/api/status`),
    ]);
    const system = await systemResponse.json();
    const status = await statusResponse.json();
    const rows = [];
    if (status.model) rows.push(listRow("Modèle IA", "Moteur de raisonnement local", String(status.model)));
    if (status.version) rows.push(listRow("Version KIRA", "Instance locale", String(status.version)));
    if (system.cpu_cores) rows.push(listRow("Processeur", "Cœurs logiques", String(system.cpu_cores)));
    if (system.memory_total_gb !== undefined) {
      rows.push(listRow("Mémoire vive", system.memory_used_gb + " Go utilisés sur " + system.memory_total_gb + " Go", Math.round(system.memory_percent) + "%"));
    }
    if (system.disk_percent !== undefined) rows.push(listRow("Disque système", "Espace utilisé", Math.round(system.disk_percent) + "%"));
    if (system.gpu) rows.push(listRow("Carte graphique", "Contrôleur vidéo détecté", String(system.gpu)));
    if (system.uptime_h !== undefined) rows.push(listRow("Machine allumée depuis", "Temps de fonctionnement", Math.round(system.uptime_h) + " h"));
    list.innerHTML = rows.length > 0
      ? rows.join("")
      : '<div class="task-empty">Aucune information disponible</div>';
  } catch (error) {
    list.innerHTML = '<div class="task-empty">Backend indisponible</div>';
  }
}
window.loadSystemFull = loadSystemFull;

async function loadParamInfo() {
  const info = document.getElementById("param-model");
  try {
    const response = await fetch(`${API_BASE}/api/status`);
    const data = await response.json();
    info.innerHTML = data.model
      ? "Modèle : <strong>" + escapeHtml(String(data.model)) + "</strong><br>Version : " + escapeHtml(String(data.version || "?")) + "<br>Backend : " + (data.online ? "en ligne" : "hors ligne")
      : "Backend démarré sans modèle configuré.";
  } catch (error) {
    info.textContent = "Backend KIRA indisponible — l'interface fonctionne en mode dégradé.";
  }
}
window.loadParamInfo = loadParamInfo;

// ─────────────────────────────────────────────
// Outils & actions rapides
// ─────────────────────────────────────────────

window.promptWebSearch = function() {
  const query = window.prompt("Recherche web — que doit chercher KIRA ?");
  if (query && query.trim()) window.quickCmd("search for " + query.trim());
};

window.promptLearn = async function() {
  const url = window.prompt("URL de la page à apprendre :");
  if (!url || !url.trim()) return;
  try {
    const response = await fetch(`${API_BASE}/api/web/learn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url.trim() }),
    });
    const data = await response.json();
    showToast(data.error ? "Échec : " + data.error : "Page apprise et mémorisée");
  } catch (error) {
    showToast("Backend indisponible");
  }
};

window.promptAddTask = async function() {
  const title = window.prompt("Nouvelle tâche (ex. : rappelle-moi d'appeler dans 5 minutes) :");
  if (!title || !title.trim()) return;
  try {
    const response = await fetch(`${API_BASE}/api/task`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title.trim(), type: "todo" }),
    });
    const data = await response.json();
    showToast(data.error ? "Échec : " + data.error : "Tâche ajoutée");
    updateTasks();
    if (activeView === "taches") loadTasksFull();
  } catch (error) {
    showToast("Backend indisponible");
  }
};

window.promptRemember = async function() {
  const text = window.prompt("Que faut-il mémoriser ?");
  if (!text || !text.trim()) return;
  try {
    const response = await fetch(`${API_BASE}/api/remember`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text.trim(), category: "note" }),
    });
    const data = await response.json();
    showToast(data.error ? "Échec : " + data.error : "Mémorisé");
  } catch (error) {
    showToast("Backend indisponible");
  }
};

// ─────────────────────────────────────────────
// Navigation du dock, cloche, paramètres, veille
// ─────────────────────────────────────────────

NAV_IDS.forEach((id) => {
  const btn = document.getElementById("nav-" + id);
  if (!btn) return;
  btn.addEventListener("click", () => {
    if (id === "accueil" || id === "conversation") {
      closeView();
      if (id === "conversation") commandInput.focus();
    } else {
      openView(id);
    }
  });
});

document.getElementById("bell-btn").addEventListener("click", () => openView("taches"));
document.getElementById("settings-btn").addEventListener("click", () => openView("parametres"));
document.getElementById("agents-add").addEventListener("click", () => openView("agents"));
document.getElementById("tasks-open").addEventListener("click", () => openView("taches"));
document.getElementById("view-close").addEventListener("click", closeView);

const standby = document.getElementById("standby");
document.getElementById("power-btn").addEventListener("click", () => {
  stopSpeaking();
  standby.classList.remove("hidden");
});
standby.addEventListener("click", () => {
  standby.classList.add("hidden");
});

// ─────────────────────────────────────────────
// Paramètres : voix, micro
// ─────────────────────────────────────────────

const voiceSelect = document.getElementById("voice-select");
const microSelect = document.getElementById("micro-select");

try {
  const savedVoice = localStorage.getItem("kira.voice");
  if (savedVoice) voiceSelect.value = savedVoice;
  const savedMicro = localStorage.getItem("kira.micro");
  if (savedMicro) microSelect.value = savedMicro;
} catch { /* stockage indisponible */ }

voiceSelect.addEventListener("change", () => {
  try { localStorage.setItem("kira.voice", voiceSelect.value); } catch { /* optionnel */ }
  showToast("Voix enregistrée : " + voiceSelect.options[voiceSelect.selectedIndex].text);
});

microSelect.addEventListener("change", () => {
  try { localStorage.setItem("kira.micro", microSelect.value); } catch { /* optionnel */ }
  showToast("Langue du micro enregistrée");
});

/* =========================================================
   MOUVEMENT PILOTE PAR LA VOIX
   ========================================================= */

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let motionPreference = "auto";
try {
  const saved = localStorage.getItem("kira.motion");
  if (["auto", "on", "off"].includes(saved)) motionPreference = saved;
} catch { /* navigateurs intégrés peuvent bloquer le stockage */ }
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
  motionButton.title = "Auto suit le réglage système de mouvement réduit. On force l'animation. Off garde l'interface immobile.";
}
motionButton.addEventListener("click", () => {
  const choices = ["auto", "on", "off"];
  motionPreference = choices[(choices.indexOf(motionPreference) + 1) % choices.length];
  try { localStorage.setItem("kira.motion", motionPreference); } catch { /* optionnel */ }
  updateMotionButton();
});
motionTest.addEventListener("click", () => { motionDemoStarted = performance.now(); });
voiceTest.addEventListener("click", () => {
  if (!speech.enabled) return;
  speech.unlock();
  speak("Mon cœur bouge avec ma voix. Une courte pause. Maintenant je parle à nouveau.");
});
updateMotionButton();
let lastFrame = performance.now();
let voiceRotation = 0;

/* =========================================================
   ANIMATION
   ========================================================= */

const voiceBarEl = document.getElementById("bar-voice");
const voiceValEl = document.getElementById("val-voice");

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
  // Mouvement réduit : indice de luminosité discret, sans déformation.
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

  // Barre d'activité vocale (donnée réelle : énergie audio instantanée)
  if (voiceBarEl) {
    voiceBarEl.style.width = (Math.min(100, level * 100)).toFixed(0) + "%";
    voiceValEl.textContent = Math.round(level * 100) + "%";
  }

  // La machinerie tourne lentement ; l'avatar reste face à vous mais
  // respire avec la voix comme le reste du réacteur.
  reactor.rotation.y = motionTime * 0.09;
  reactor.rotation.x = Math.sin(motionTime * 0.18) * 0.08;
  reactor.scale.set(1.05 + energy * 0.12, 1.05 + energy * 0.23, 1.05 + energy * 0.12);
  reactor.position.y = Math.sin(motionTime * 3.5) * energy * 0.14;
  // L'avatar reste stable et humain ; seule une respiration légère l'anime.
  avatarGroup.scale.set(1 + energy * 0.02, 1 + energy * 0.045, 1);
  armorGroup.rotation.y = -motionTime * 0.08;
  verticalArmor.rotation.y = motionTime * 0.05;
  halo.rotation.z = motionTime * 1.8 + voiceRotation * 0.5;
  halo.scale.setScalar(1 + low * 0.25);
  haloMat.opacity = 0.3 + light * 0.12;
  neuralCore.rotation.z = motionTime * 0.35 + voiceRotation * 0.65;
  neuralCore.scale.setScalar(1 + energy * 0.2);
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
  beamMat.opacity = 0.4 + light * 0.14;

  // Déplacement des anneaux, indépendant du framerate.
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
  bloomPass.strength = 1.1 + light * 0.16;

  reactorParticles.rotation.y = motionTime * 0.025;
  reactorParticles.rotation.x = Math.sin(motionTime * 0.15) * 0.15;
  reactorParticles.scale.setScalar(1 + low * 0.05);
  particleMat.size = 0.028 + high * 0.012;

  composer.render();
}

/* =========================================================
   MÉMOIRE DE SESSION PRÉCÉDENTE
   ========================================================= */

async function loadBootHistory() {
  try {
    const response = await fetch(`${API_BASE}/api/history?limit=6`);
    const data = await response.json();
    const messages = Array.isArray(data.messages) ? data.messages : [];
    if (messages.length === 0) return;
    addHistoryDivider();
    messages.forEach((message) => {
      addMessage(
        message.role === "user" ? "Vous" : "KIRA",
        message.content,
        message.role === "user",
        "history-block"
      );
    });
    const conversation = document.getElementById("conversation");
    conversation.scrollTop = 0;
  } catch (error) {
    // Pas d'historique disponible
  }
}

/* =========================================================
   DÉMARRAGE
   ========================================================= */

addMessage(
  "KIRA",
  "Bonjour. Tous les systèmes sont nominaux — je suis prête à vous accompagner.",
  false
);

updateTelemetry();
updateTasks();
updatePlugins();
renderAgents();
loadBootHistory();

setInterval(updateTelemetry, 3000);
setInterval(updateTasks, 5000);
setInterval(updatePlugins, 60000);

animate();
