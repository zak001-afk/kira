/* =========================================================
   KIRA // NEURAL INTERFACE
   Bridges the browser to the local agent (kira_server.py).

   Two independent layers:
     1. the HUD — commands, conversation, telemetry (no dependencies)
     2. the visuals — matrix rain + 3D reactor (optional Three.js)
   If Three.js cannot load (offline, blocked CDN, no WebGL) the HUD keeps
   working and a CSS core takes the reactor's place.
   ========================================================= */

/* =========================================================
   CONFIG
   ========================================================= */

const POLL_MS = 1500;

const RED = 0xff2020;
const RED_BRIGHT = 0xff4545;
const RED_DARK = 0x650808;
const RED_DEEP = 0x260303;

/* How the reactor reacts to what KIRA is doing, mirroring the desktop orb. */
const STATE_STYLE = {
  READY: { label: "STANDBY", spin: 1.0, bloom: 1.45, energy: 0.2, key: "ready" },
  LISTENING: { label: "LISTENING", spin: 2.4, bloom: 2.1, energy: 0.42, key: "listening" },
  THINKING: { label: "THINKING", spin: 3.4, bloom: 2.6, energy: 0.55, key: "thinking" },
  CONFIRM: { label: "AWAITING CONFIRM", spin: 1.4, bloom: 2.0, energy: 0.35, key: "confirm" },
  EXECUTING: { label: "EXECUTING", spin: 4.2, bloom: 3.0, energy: 0.65, key: "executing" },
  SPEAKING: { label: "SPEAKING", spin: 1.8, bloom: 2.4, energy: 0.5, key: "speaking" },
  ERROR: { label: "FAULT", spin: 0.8, bloom: 1.9, energy: 0.3, key: "error" },
};

const appState = {
  state: "READY",
  style: STATE_STYLE.READY,
  online: false,
  mode: "connecting",
  reason: "",
  speak: localStorage.getItem("kira.speak") !== "off",
  busy: false,
  pendingConfirm: false,
};

/* =========================================================
   DOM HELPERS
   ========================================================= */

const $ = (id) => document.getElementById(id);

const conversation = $("conversation");
const thinking = $("thinking");
const thinkingLabel = $("thinking-label");
const commandInput = $("command");
const sendButton = $("send");
const micButton = $("mic");
const confirmBar = $("confirm-bar");
const confirmText = $("confirm-text");
const onlineChip = $("online-chip");
const onlineText = $("online-text");
const modeLabel = $("mode-label");

/* =========================================================
   API CLIENT
   ========================================================= */

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

const apiState = () => api("/api/state");
const apiHistory = (limit = 30) => api(`/api/history?limit=${limit}`);
const apiReset = () => api("/api/reset", { method: "POST", body: "{}" });
const apiCommand = (text, confirm = false) =>
  api("/api/command", {
    method: "POST",
    body: JSON.stringify({ text, confirm }),
  });

/* =========================================================
   CONVERSATION
   ========================================================= */

const ROLE_LABEL = { kira: "KIRA", you: "YOU", mind: "MIND" };

function addMessage(role, text, kind = "message") {
  if (!text) return;

  const entry = document.createElement("div");
  entry.className = `msg ${role === "you" ? "you" : "kira"}`;
  if (kind === "mind") entry.classList.add("mind");
  if (kind === "proactive") entry.classList.add("proactive");
  if (kind === "failed") entry.classList.add("failed");

  const meta = document.createElement("div");
  meta.className = "msg-meta";
  const time = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  meta.innerHTML = `${ROLE_LABEL[role] || "KIRA"}&nbsp; // &nbsp;<span class="msg-time">${time}</span>`;
  if (kind === "mind") meta.innerHTML = `KIRA&nbsp;//&nbsp;INNER MONOLOGUE&nbsp;//&nbsp;<span class="msg-time">${time}</span>`;

  const body = document.createElement("div");
  body.className = "msg-text";
  body.textContent = text;

  entry.append(meta, body);
  conversation.append(entry);
  trimConversation();
  conversation.scrollTop = conversation.scrollHeight;
  return entry;
}

function trimConversation(limit = 120) {
  while (conversation.children.length > limit) {
    conversation.removeChild(conversation.firstElementChild);
  }
}

function showThinking(on, label = "PROCESSING") {
  thinking.hidden = !on;
  thinkingLabel.textContent = label;
}

/* =========================================================
   SPEECH (browser voice — platform independent)
   ========================================================= */

let preferredVoice = null;

function pickVoice() {
  if (!("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices() || [];
  const preferred = [
    "aria", "jenny", "michelle", "sonia", "zira", "hazel",
    "samantha", "female",
  ];
  for (const token of preferred) {
    const match = voices.find((voice) =>
      (voice.name || "").toLowerCase().includes(token),
    );
    if (match) return match;
  }
  return voices.find((voice) => (voice.lang || "").startsWith("en")) || null;
}

if ("speechSynthesis" in window) {
  pickVoice();
  window.speechSynthesis.onvoiceschanged = () => {
    preferredVoice = pickVoice();
  };
}

function speak(text) {
  if (!appState.speak || !("speechSynthesis" in window) || !text) return;
  const cleaned = String(text)
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "")
    .replace(/\s{2,}/g, " ")
    .trim();
  if (!cleaned) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(cleaned);
  if (!preferredVoice) preferredVoice = pickVoice();
  if (preferredVoice) utterance.voice = preferredVoice;
  utterance.rate = 0.98; // a touch slower reads warmer
  utterance.pitch = 1.02;
  window.speechSynthesis.speak(utterance);
}

function setSpeaking(on) {
  if (on && appState.state !== "ERROR") {
    setActivity("SPEAKING");
    window.setTimeout(() => {
      if (appState.state === "SPEAKING") setActivity("READY");
    }, 2200);
  }
}

/* =========================================================
   STATE / TELEMETRY
   ========================================================= */

function setActivity(state) {
  const style = STATE_STYLE[state] || STATE_STYLE.READY;
  appState.state = state;
  appState.style = style;

  const row = $("activity-row");
  $("activity").textContent = style.label;
  row.className = `activity ${style.key}`;
}

function setOnline(online, mode, reason) {
  appState.online = online;
  appState.mode = mode;
  appState.reason = reason || "";

  onlineChip.className = "online";
  if (mode === "simulation") {
    onlineChip.classList.add("simulation");
    onlineText.textContent = "SIMULATION";
    modeLabel.textContent = "DEMO INSTANCE — NO HARDWARE CONTROL";
  } else if (online) {
    onlineText.textContent = "ONLINE";
    modeLabel.textContent = "LOCAL INSTANCE";
  } else {
    onlineChip.classList.add("offline");
    onlineText.textContent = "OFFLINE";
    modeLabel.textContent = "BACKEND UNAVAILABLE";
  }

  const note = $("backend-note");
  note.textContent = !online && reason ? `backend: ${reason}` : "";
  if (mode === "simulation") {
    note.textContent = "demo mode: replies are simulated";
  }
}

const percent = (value) =>
  typeof value === "number" ? `${Math.round(value)}%` : "—";

function setMeter(id, value) {
  const bar = $(`${id}-bar`);
  if (bar) bar.style.width = typeof value === "number" ? `${value}%` : "0%";
}

function applyTelemetry(data) {
  setOnline(data.online, data.mode, data.reason);

  if (data.state && data.state !== "SPEAKING") setActivity(data.state);

  $("cpu").textContent = percent(data.cpu);
  $("memory").textContent = percent(data.memory);
  $("disk").textContent = percent(data.disk);
  setMeter("cpu", data.cpu);
  setMeter("memory", data.memory);

  if (data.battery) {
    $("battery").textContent = `${Math.round(data.battery.percent)}%${
      data.battery.plugged ? " ⚡" : ""
    }`;
  } else {
    $("battery").textContent = "—";
  }

  $("model").textContent = data.model && data.model !== "—" ? data.model : "LOCAL NEURAL ENGINE";
  $("skills").textContent = data.skills ?? "—";
  $("episodes").textContent = data.episodes ?? "—";

  // unprompted messages (watchdog alerts, reminders) arrive through polling
  for (const message of data.queue || []) {
    addMessage("kira", message, "proactive");
    speak(message);
  }
}

async function poll() {
  try {
    applyTelemetry(await apiState());
  } catch (error) {
    setOnline(false, "offline", String(error.message || error));
  }
}

/* =========================================================
   COMMAND FLOW
   ========================================================= */

function setBusy(busy, label = "PROCESSING") {
  appState.busy = busy;
  sendButton.disabled = busy;
  micButton.disabled = busy;
  showThinking(busy, label);
  if (busy) setActivity(label === "LISTENING" ? "LISTENING" : "THINKING");
}

function renderResult(data) {
  if (data.thought) addMessage("kira", data.thought, "mind");
  if (data.reply) {
    addMessage("kira", data.reply, data.kind === "error" ? "failed" : "message");
    if (data.kind !== "error") speak(data.reply);
  }
  if (data.needs_confirmation) {
    appState.pendingConfirm = true;
    confirmText.textContent = `Confirm: ${data.reply}`;
    confirmBar.hidden = false;
    setActivity("CONFIRM");
  }
}

async function sendCommand(text) {
  const value = String(text || "").trim();
  if (!value || appState.busy) return;

  addMessage("you", value);
  commandInput.value = "";
  setBusy(true);

  try {
    const data = await apiCommand(value);
    renderResult(data);
  } catch (error) {
    addMessage("kira", `I could not reach my local brain, sir — ${error}`, "failed");
  } finally {
    setBusy(false);
    if (!appState.pendingConfirm) setActivity("READY");
    commandInput.focus();
  }
}

async function answerConfirmation(confirmed) {
  confirmBar.hidden = true;
  appState.pendingConfirm = false;
  setBusy(true, "EXECUTING");
  try {
    const data = await apiCommand("", confirmed);
    renderResult({ ...data, needs_confirmation: false });
    addMessage("you", confirmed ? "confirmed" : "cancelled", "mind");
  } catch (error) {
    addMessage("kira", `The confirmation failed, sir — ${error}`, "failed");
  } finally {
    setBusy(false);
    setActivity("READY");
  }
}

async function listenOnce() {
  if (appState.busy) return;
  micButton.classList.add("listening");
  micButton.textContent = "HEARING";
  setBusy(true, "LISTENING");
  try {
    const data = await api("/api/listen", { method: "POST", body: "{}" });
    if (data.text) {
      await sendCommand(data.text);
    } else if (data.error) {
      addMessage("kira", `My microphone is unavailable, sir — ${data.error}`, "failed");
    } else {
      addMessage("kira", "I didn't catch that, sir.", "failed");
    }
  } catch (error) {
    addMessage("kira", `Microphone error, sir — ${error}`, "failed");
  } finally {
    micButton.classList.remove("listening");
    micButton.textContent = "MIC";
    setBusy(false);
    setActivity("READY");
  }
}

/* =========================================================
   CONTROLS
   ========================================================= */

sendButton.addEventListener("click", () => sendCommand(commandInput.value));
commandInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") sendCommand(commandInput.value);
});

micButton.addEventListener("click", listenOnce);

$("confirm-yes").addEventListener("click", () => answerConfirmation(true));
$("confirm-no").addEventListener("click", () => answerConfirmation(false));

document.querySelectorAll("#quick-actions button").forEach((button) => {
  button.addEventListener("click", () => sendCommand(button.dataset.command));
});

const speakToggle = $("speak-toggle");
function renderSpeakToggle() {
  speakToggle.textContent = `VOICE: ${appState.speak ? "ON" : "OFF"}`;
  speakToggle.classList.toggle("active", appState.speak);
}
speakToggle.addEventListener("click", () => {
  appState.speak = !appState.speak;
  localStorage.setItem("kira.speak", appState.speak ? "on" : "off");
  if (!appState.speak && "speechSynthesis" in window) window.speechSynthesis.cancel();
  renderSpeakToggle();
});
renderSpeakToggle();

$("reset-chat").addEventListener("click", async () => {
  conversation.innerHTML = "";
  try {
    await apiReset();
  } catch (error) {
    /* the conversation is local; a failed reset still clears the view */
  }
  addMessage("kira", "Fresh start, sir.");
});

/* =========================================================
   MATRIX RAIN
   ========================================================= */

const GLYPHS = "0123456789+-*/\\|=<>[]{}#$%&@?!:;^~";

const matrixCanvas = $("matrix");
const matrixContext = matrixCanvas.getContext("2d");
const matrixFontSize = 14;

let matrixColumns = [];
let matrixWidth = 0;
let matrixHeight = 0;

function resizeMatrix() {
  matrixWidth = matrixCanvas.width = window.innerWidth;
  matrixHeight = matrixCanvas.height = window.innerHeight;
  const count = Math.floor(matrixWidth / matrixFontSize);
  matrixColumns = new Array(count).fill(0).map(() => ({
    head: Math.random() * (matrixHeight / matrixFontSize),
    speed: 0.35 + Math.random() * 0.75,
    length: 6 + Math.floor(Math.random() * 12),
    offset: Math.floor(Math.random() * 500),
  }));
}

function glyphFor(index) {
  let mixed = (index * 2654435761) % 4294967296;
  mixed ^= mixed >> 13;
  return GLYPHS[mixed % GLYPHS.length];
}

function drawMatrix() {
  // translucent wipe leaves the classic fading trails
  matrixContext.fillStyle = "rgba(1, 1, 1, 0.10)";
  matrixContext.fillRect(0, 0, matrixWidth, matrixHeight);
  matrixContext.font = `${matrixFontSize}px Consolas, monospace`;
  matrixContext.textAlign = "center";

  const boost =
    { thinking: 2.2, executing: 2.8, listening: 1.6, speaking: 1.4 }[
      appState.style.key
    ] || 1.0;

  for (let i = 0; i < matrixColumns.length; i++) {
    const column = matrixColumns[i];
    const x = i * matrixFontSize + matrixFontSize / 2;
    const headY = column.head * matrixFontSize;

    // the falling head is white-hot, the tail fades into the dark
    for (let step = 0; step < column.length; step++) {
      const y = headY - step * matrixFontSize;
      if (y < -matrixFontSize || y > matrixHeight + matrixFontSize) continue;
      const intensity = step === 0 ? 1 : (1 - step / column.length) ** 1.6;
      if (step === 0) {
        matrixContext.fillStyle = "rgba(255, 160, 160, 0.95)";
      } else {
        const red = Math.round(40 + 175 * intensity);
        matrixContext.fillStyle = `rgba(${red}, ${Math.round(
          10 + 30 * intensity,
        )}, ${Math.round(10 + 30 * intensity)}, ${0.15 + intensity * 0.7})`;
      }
      matrixContext.fillText(
        glyphFor(column.offset + Math.round(headY / matrixFontSize) - step),
        x,
        y,
      );
    }

    column.head += column.speed * boost;
    if (headY > matrixHeight + column.length * matrixFontSize && Math.random() > 0.9) {
      column.head = -Math.random() * 20;
      column.speed = 0.35 + Math.random() * 0.75;
      column.length = 6 + Math.floor(Math.random() * 12);
    }
  }
}

/* =========================================================
   3D REACTOR (optional — degrades to the CSS core)
   ========================================================= */

let reactorAPI = null;

/* Any failure here — missing WebGL, a lost GPU context, an import problem —
   must cost the user the reactor, never the interface. */
async function startReactor() {
  try {
    await buildReactor();
  } catch (error) {
    document.body.classList.add("no-webgl");
    console.info(
      "KIRA: 3D reactor unavailable, using the CSS core —",
      error && error.message ? error.message : error,
    );
  }
}

async function buildReactor() {
  const THREE = await import("three");
  const { EffectComposer } = await import("three/addons/postprocessing/EffectComposer.js");
  const { RenderPass } = await import("three/addons/postprocessing/RenderPass.js");
  const { UnrealBloomPass } = await import("three/addons/postprocessing/UnrealBloomPass.js");

  const container = $("scene-container");

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x010101);

  const camera = new THREE.PerspectiveCamera(
    45,
    window.innerWidth / window.innerHeight,
    0.1,
    1000,
  );
  camera.position.set(0, 0, 15);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  container.appendChild(renderer.domElement);

  const ambient = new THREE.AmbientLight(0x120000, 2);
  scene.add(ambient);

  const redLight = new THREE.PointLight(RED, 18, 12);
  redLight.position.set(0, 0, 2);
  scene.add(redLight);

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloomPass = new UnrealBloomPass(
    new THREE.Vector2(window.innerWidth, window.innerHeight),
    1.8,
    0.75,
    0.15,
  );
  bloomPass.threshold = 0.12;
  bloomPass.strength = 1.45;
  bloomPass.radius = 0.65;
  composer.addPass(bloomPass);

  /* ---------------------------------------------------------
     THE REACTOR
     --------------------------------------------------------- */

  const reactor = new THREE.Group();
  scene.add(reactor);
  reactor.scale.setScalar(1.05);

  const shell = new THREE.Mesh(
    new THREE.SphereGeometry(2.25, 96, 96),
    new THREE.MeshStandardMaterial({
      color: 0x050505,
      metalness: 0.95,
      roughness: 0.28,
      emissive: 0x180000,
      emissiveIntensity: 0.18,
      transparent: true,
      opacity: 0.22,
      depthWrite: false,
    }),
  );
  reactor.add(shell);

  const wireShell = new THREE.Mesh(
    new THREE.SphereGeometry(2.29, 48, 48),
    new THREE.MeshBasicMaterial({
      color: 0xff1515,
      wireframe: true,
      transparent: true,
      opacity: 0.035,
    }),
  );
  reactor.add(wireShell);

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

  const armorGroup = new THREE.Group();
  reactor.add(armorGroup);
  for (let i = 0; i < 12; i++) {
    const angle = (i / 12) * Math.PI * 2;
    const plate = new THREE.Mesh(new THREE.BoxGeometry(0.95, 0.12, 0.38), armorMaterial);
    plate.position.set(Math.cos(angle) * 1.72, Math.sin(angle) * 1.72, 0);
    plate.rotation.z = angle;
    armorGroup.add(plate);

    const edge = new THREE.Mesh(new THREE.BoxGeometry(0.98, 0.025, 0.4), armorEdgeMaterial);
    edge.position.copy(plate.position);
    edge.rotation.copy(plate.rotation);
    edge.position.z += 0.24;
    armorGroup.add(edge);
  }

  const verticalArmor = new THREE.Group();
  reactor.add(verticalArmor);
  for (let i = 0; i < 8; i++) {
    const angle = (i / 8) * Math.PI * 2;
    const plate = new THREE.Mesh(new THREE.BoxGeometry(0.32, 1.15, 0.1), armorMaterial);
    plate.position.set(Math.cos(angle) * 1.95, 0, Math.sin(angle) * 1.95);
    plate.rotation.y = -angle;
    verticalArmor.add(plate);
  }

  const energySphere = new THREE.Mesh(
    new THREE.SphereGeometry(1.55, 64, 64),
    new THREE.MeshBasicMaterial({
      color: 0xff0808,
      transparent: true,
      opacity: 0.2,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );
  reactor.add(energySphere);

  const core = new THREE.Mesh(
    new THREE.SphereGeometry(0.42, 64, 64),
    new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false }),
  );
  reactor.add(core);

  const coreGlow = new THREE.Mesh(
    new THREE.SphereGeometry(0.78, 64, 64),
    new THREE.MeshBasicMaterial({
      color: 0xff1515,
      transparent: true,
      opacity: 0.42,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      toneMapped: false,
    }),
  );
  reactor.add(coreGlow);

  const whiteGlowMaterial = new THREE.MeshBasicMaterial({
    color: 0xffdddd,
    transparent: true,
    opacity: 0.28,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
  });
  const whiteGlow = new THREE.Mesh(new THREE.SphereGeometry(0.62, 64, 64), whiteGlowMaterial);
  reactor.add(whiteGlow);

  /* neural processor */
  const neuralCore = new THREE.Group();
  reactor.add(neuralCore);

  const innerRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.62, 0.035, 12, 96),
    new THREE.MeshBasicMaterial({
      color: 0xff2020,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
    }),
  );
  innerRing.rotation.x = Math.PI / 2;
  neuralCore.add(innerRing);

  const secondRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.92, 0.018, 12, 128),
    new THREE.MeshBasicMaterial({
      color: 0xff3030,
      transparent: true,
      opacity: 0.65,
      blending: THREE.AdditiveBlending,
    }),
  );
  secondRing.rotation.x = Math.PI / 2;
  neuralCore.add(secondRing);

  const coreFrame = new THREE.Mesh(
    new THREE.CylinderGeometry(0.48, 0.48, 0.16, 32),
    new THREE.MeshStandardMaterial({
      color: 0x090909,
      metalness: 1,
      roughness: 0.2,
      emissive: 0x220000,
      emissiveIntensity: 0.3,
    }),
  );
  coreFrame.rotation.x = Math.PI / 2;
  neuralCore.add(coreFrame);

  const energyDisc = new THREE.Mesh(
    new THREE.CylinderGeometry(0.34, 0.34, 0.18, 64),
    new THREE.MeshBasicMaterial({
      color: 0xff0808,
      transparent: true,
      opacity: 1.0,
      blending: THREE.AdditiveBlending,
    }),
  );
  energyDisc.rotation.x = Math.PI / 2;
  energyDisc.position.z = 0.11;
  neuralCore.add(energyDisc);

  const neuralOrbit1 = new THREE.Group();
  const neuralOrbit2 = new THREE.Group();
  neuralCore.add(neuralOrbit1, neuralOrbit2);

  const neuralOrbitMaterial = new THREE.MeshBasicMaterial({
    color: 0xff1818,
    transparent: true,
    opacity: 0.55,
    blending: THREE.AdditiveBlending,
  });
  const neuralOrbitGeometry = new THREE.TorusGeometry(1.15, 0.012, 8, 128);
  neuralOrbit1.add(new THREE.Mesh(neuralOrbitGeometry, neuralOrbitMaterial));
  const orbitRing2 = new THREE.Mesh(neuralOrbitGeometry, neuralOrbitMaterial.clone());
  orbitRing2.rotation.x = Math.PI / 2;
  orbitRing2.rotation.z = Math.PI / 3;
  neuralOrbit2.add(orbitRing2);

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
    const beam = new THREE.Mesh(new THREE.BoxGeometry(0.025, 1.7, 0.025), beamMaterial);
    beam.position.set(Math.cos(angle) * 0.95, Math.sin(angle) * 0.95, 0);
    beam.rotation.z = angle;
    beamGroup.add(beam);
  }

  const halo = new THREE.Mesh(
    new THREE.RingGeometry(0.62, 0.82, 96),
    new THREE.MeshBasicMaterial({
      color: 0xff2020,
      transparent: true,
      opacity: 0.35,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );
  halo.rotation.x = Math.PI / 2;
  reactor.add(halo);

  const reactorLight = new THREE.PointLight(0xff1010, 11, 8);
  reactor.add(reactorLight);

  /* orbital rings */
  const ringMaterials = [];
  function createReactorRing(radius, tube, rotation, opacity) {
    const material = new THREE.MeshBasicMaterial({
      color: 0xff1010,
      transparent: true,
      opacity,
    });
    const ring = new THREE.Mesh(new THREE.TorusGeometry(radius, tube, 12, 180), material);
    ring.rotation.set(rotation.x, rotation.y, rotation.z);
    reactor.add(ring);
    ringMaterials.push(material);
    return ring;
  }

  const ring1 = createReactorRing(3.05, 0.012, new THREE.Euler(1.1, 0.15, 0.25), 0.28);
  const ring2 = createReactorRing(2.75, 0.018, new THREE.Euler(0.25, 1.15, 0.5), 0.2);
  const ring3 = createReactorRing(3.35, 0.009, new THREE.Euler(1.55, 0.55, 0.2), 0.14);
  const ring4 = createReactorRing(2.45, 0.008, new THREE.Euler(0.4, 0.8, 1.2), 0.14);

  /* energy particles */
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
  const particleGeometry = new THREE.BufferGeometry();
  particleGeometry.setAttribute("position", new THREE.BufferAttribute(particlePositions, 3));
  const reactorParticles = new THREE.Points(
    particleGeometry,
    new THREE.PointsMaterial({
      color: 0xff2020,
      size: 0.025,
      transparent: true,
      opacity: 0.38,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );
  reactor.add(reactorParticles);

  /* ---------------------------------------------------------
     ANIMATION
     --------------------------------------------------------- */

  let spinPhase = 0;

  function animate() {
    requestAnimationFrame(animate);

    const time = performance.now() * 0.001;
    const style = appState.style;

    // KIRA's state drives how hard the reactor works
    spinPhase += 0.0016 * style.spin;

    reactor.rotation.y = spinPhase * 3 + time * 0.12;
    reactor.rotation.x = Math.sin(time * 0.18) * 0.08;
    armorGroup.rotation.y = -time * 0.08 * style.spin;
    verticalArmor.rotation.y = time * 0.05 * style.spin;

    halo.rotation.z = time * 1.8 * style.spin;
    neuralCore.rotation.z = time * 0.35 * style.spin;
    innerRing.rotation.z = time * 1.2 * style.spin;
    secondRing.rotation.z = -time * 0.8 * style.spin;
    neuralOrbit1.rotation.x = time * 0.7 * style.spin;
    neuralOrbit1.rotation.y = time * 0.4 * style.spin;
    neuralOrbit2.rotation.x = -time * 0.5 * style.spin;
    neuralOrbit2.rotation.z = time * 0.8 * style.spin;
    beamGroup.rotation.z = -time * 0.25 * style.spin;

    ring1.rotation.z += 0.0025 * style.spin;
    ring1.rotation.x += 0.001 * style.spin;
    ring2.rotation.y += 0.003 * style.spin;
    ring2.rotation.z -= 0.0012 * style.spin;
    ring3.rotation.x -= 0.0015 * style.spin;
    ring3.rotation.y += 0.0018 * style.spin;
    ring4.rotation.z += 0.0035 * style.spin;

    const energy = style.energy;
    energySphere.scale.setScalar(1 + Math.sin(time * 2.8) * (0.055 + energy * 0.06));
    energySphere.material.opacity = 0.14 + energy * 0.28;
    energyDisc.scale.setScalar(1 + Math.sin(time * 4) * 0.08);

    core.scale.setScalar(1 + Math.sin(time * 4.5) * (0.12 + energy * 0.05));
    coreGlow.scale.setScalar(1 + Math.sin(time * 3.2) * 0.16);
    whiteGlow.scale.setScalar(1 + Math.sin(time * 4.5) * 0.1);
    whiteGlowMaterial.opacity = 0.22 + Math.sin(time * 4.5) * 0.06;

    reactorLight.intensity = (9 + Math.sin(time * 4.5) * 3) * (0.7 + energy);
    ringMaterials.forEach((material, index) => {
      material.opacity = (0.14 + index * 0.05) * (0.7 + energy * 1.1);
    });

    reactorParticles.rotation.y = time * 0.025 * style.spin;
    reactorParticles.rotation.x = Math.sin(time * 0.15) * 0.15;

    bloomPass.strength = style.bloom;

    composer.render();
  }

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    composer.setSize(window.innerWidth, window.innerHeight);
    resizeMatrix();
  });

  animate();
  reactorAPI = { scene, reactor };
}

/* =========================================================
   MATRIX LOOP
   ========================================================= */

function matrixLoop() {
  requestAnimationFrame(matrixLoop);
  drawMatrix();
}

/* =========================================================
   BOOT
   ========================================================= */

async function boot() {
  resizeMatrix();
  window.addEventListener("resize", resizeMatrix);

  // visual layers first so the interface is alive immediately
  matrixLoop();
  startReactor();

  // restore the conversation the server already knows about
  try {
    const { messages } = await apiHistory(24);
    if (messages && messages.length) {
      conversation.innerHTML = "";
      for (const message of messages) {
        addMessage(
          message.role === "you" ? "you" : "kira",
          message.text,
          message.kind === "mind" ? "mind" : message.kind || "message",
        );
      }
    }
  } catch (error) {
    /* no history yet — the greeting stands */
  }

  await poll();
  setInterval(poll, POLL_MS);
  commandInput.focus();
  console.info("KIRA neural interface ready");
}

boot();
