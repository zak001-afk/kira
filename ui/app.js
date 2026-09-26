import { I18n, UI_LANGUAGES, interfaceLanguage } from "./i18n.mjs";
import { AGENTS, delegateFor } from "./agents.mjs";
import { speechLocale, baseLanguage, FALLBACK_LANGUAGES, VOICE_SAMPLES } from "./locale.mjs";
import { SpeechPlayer } from "./speech.mjs?v=open-19";
import { lipDemoPose } from "./lips.mjs";
import { Hologram } from "./hologram.mjs?v=open-19";

/* KIRA / cockpit controller. The desktop and browser share the same local UI.
   API calls stay on this origin; kira_ui.py proxies them to the local backend. */
const $ = (id) => document.getElementById(id);
const startedAt = performance.now();
const i18n = new I18n(preference("kira.uiLanguage", UI_LANGUAGES, interfaceLanguage(navigator.language)));
const t = (message, values) => i18n.t(message, values);
i18n.apply(document);
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const pendingRequests = new Set();
const intervals = [];
let destroyed = false;
let commandPending = false;
let commandCount = 0;
let messageSequence = 0;
let speechState = "READY";
let activityState = "STANDBY";
let currentPanel = null;
let languageRevision = 0;
let motionDemoStarted = -Infinity;
let lipDemoStarted = -Infinity;
let lipsEnabled = preference("kira.lips", ["on", "off"], "on") === "on";
let lastFrame = -Infinity;
let animationId;
let toastTimer;
let errorTimer;
let recognition = null;
let listening = false;
let motionPreference = preference("kira.motion", ["auto", "on", "off"], "auto");
let speechEnabled = preference("kira.voice", ["on", "off"], "on") === "on";
let voiceLanguage = readLanguagePreference("kira.language", "auto");
let replyPreference = baseLanguage(readLanguagePreference("kira.replyLanguage", "auto"));
let lastReplyLanguage = baseLanguage(readLanguagePreference("kira.lastReplyLanguage", i18n.language));
let hasReplyLanguage = Boolean(readLanguagePreference("kira.lastReplyLanguage", ""));
let languageCatalog = [...FALLBACK_LANGUAGES];
// Real session activity, shown in the AGENT ACTIVITY panel: each module bar
// reflects a genuine counter (commands sent, searches, opens, tasks, voice,
// CPU / memory share). Nothing here is simulated.
const sessionActivity = { commands: 0, searches: 0, opens: 0, voice: false, tasks: 0, cpu: null, memory: null };

const sparkData = { cpu: [], memory: [], disk: [], network: [] };

function drawSpark(key) {
  const line = $(`spark-${key}`);
  if (!line) return;
  const data = sparkData[key];
  if (!data.length) { line.setAttribute("points", ""); return; }
  const points = data.map((value, index) => {
    const x = (index / Math.max(1, data.length - 1)) * 60;
    const y = 13 - Math.max(0, Math.min(100, value)) / 100 * 12;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  line.setAttribute("points", points);
}

const AGENT_METRICS = {
  cpu: () => sessionActivity.cpu,
  memory: () => sessionActivity.memory,
  searches: () => Math.min(100, sessionActivity.searches * 25),
  opens: () => Math.min(100, sessionActivity.opens * 30),
  voice: () => (sessionActivity.voice ? 100 : 0),
  tasks: () => Math.min(100, sessionActivity.tasks * 25),
};

function updateAgentActivity() {
  for (const agent of AGENTS) {
    const bar = $(`agent-bar-${agent.id}`);
    if (!bar) continue;
    const value = AGENT_METRICS[agent.metric] ? AGENT_METRICS[agent.metric]() : null;
    const valid = typeof value === "number" && Number.isFinite(value);
    bar.style.width = valid ? `${Math.max(2, Math.min(100, value))}%` : "0";
    writeText(`agent-val-${agent.id}`, valid ? `${Math.round(value)}%` : "—");
    const line = document.querySelector(`.agent-link[data-agent="${agent.id}"]`);
    if (line) line.classList.toggle("hot", valid && value > 0);
    const row = agentRows.get(agent.id);
    if (row) {
      const state = row.querySelector(".agent-state span");
      if (state) state.textContent = valid && value > 0 ? t("WORKING") : t("ONLINE");
      row.classList.toggle("busy", valid && value > 0);
    }
  }
}

function renderRecentTasks(tasks) {
  const list = $("recent-tasks");
  if (!list) return;
  list.replaceChildren();
  if (!Array.isArray(tasks) || !tasks.length) {
    const empty = document.createElement("p");
    empty.className = "task-empty";
    empty.textContent = t("No recent tasks.");
    list.appendChild(empty);
    return;
  }
  tasks.slice(0, 5).forEach((task) => {
    const row = document.createElement("div");
    row.className = "recent-task";
    const icon = document.createElement("span");
    icon.className = "task-ico";
    icon.innerHTML = '<svg class="icon"><use href="#i-history" /></svg>';
    const when = document.createElement("small");
    when.className = "recent-time";
    const created = Date.parse(task.created_at || "");
    when.textContent = Number.isFinite(created)
      ? new Date(created).toTimeString().slice(0, 5) : "--:--";
    const label = document.createElement("span");
    label.textContent = task.title;
    label.title = task.title;
    const who = document.createElement("small");
    const kind = `${task.kind || ""} ${task.title || ""}`.toLowerCase();
    who.textContent = /(cherche|search|trouve|find|recherche)/.test(kind) ? t("Research Agent")
      : /(ouvre|open|lance|launch|d\u00e9marre|start)/.test(kind) ? t("Automation Agent") : "KIRA";
    row.append(icon, when, label, who);
    list.appendChild(row);
  });
}


function preference(key, choices, fallback) {
  try {
    const value = localStorage.getItem(key);
    return choices.includes(value) ? value : fallback;
  } catch { return fallback; }
}
function savePreference(key, value) {
  try { localStorage.setItem(key, value); } catch { /* Optional in embedded/private browsers. */ }
}
function readLanguagePreference(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value === "auto" || /^[a-z]{2,3}(?:-[a-z]{2})?$/i.test(value || "") ? value : fallback;
  } catch { return fallback; }
}
function effectiveReplyLanguage() { return replyPreference === "auto" ? lastReplyLanguage : replyPreference; }
function languageInfo(code) {
  return languageCatalog.find(item => item.code === baseLanguage(code)) || { code: baseLanguage(code), locale: speechLocale(code), native_name: code };
}
function activeLocale() { return languageInfo(effectiveReplyLanguage()).locale; }
function listeningLocale() { return voiceLanguage === "auto" ? activeLocale() : speechLocale(voiceLanguage); }
function updateLanguageControls() {
  $("interface-language").value = i18n.language;
  for (const [id, selected, label, useLocale] of [
    ["reply-language", replyPreference, t("Automatic — follow my question"), false],
    ["voice-language", voiceLanguage, t("Automatic — conversation language"), true],
  ]) {
    const select = $(id);
    select.replaceChildren();
    const auto = document.createElement("option");
    auto.value = "auto"; auto.textContent = label; select.appendChild(auto);
    const choices = [...languageCatalog];
    if (selected !== "auto" && !choices.some(item => (useLocale ? item.locale : item.code) === selected)) {
      choices.push({ code: baseLanguage(selected), locale: speechLocale(selected), native_name: selected });
    }
    for (const item of choices) {
      const option = document.createElement("option");
      option.value = useLocale ? item.locale : item.code;
      option.textContent = item.native_name;
      select.appendChild(option);
    }
    select.value = selected;
  }
  writeText("active-language", t("Current reply language: {language}", { language: languageInfo(effectiveReplyLanguage()).native_name }));
  if (recognition && !listening) recognition.lang = listeningLocale();
}
async function loadLanguageCatalog() {
  try {
    const data = await requestJSON("/languages");
    if (destroyed) return;
    if (Array.isArray(data.languages) && data.languages.length) {
      languageCatalog = data.languages.filter(item => /^[a-z]{2,3}$/.test(item.code) && typeof item.native_name === "string")
        .map(item => ({ ...item, locale: speechLocale(item.locale) }));
    }
    $("language-detector-warning").hidden = data.detector_available !== false;
    updateLanguageControls();
  } catch { /* Offline settings retain the bundled language choices. */ }
}
function writeText(id, value) {
  const element = $(id);
  // Optional targets are legitimate: panels can be removed from the layout.
  if (!element) return;
  if (element.textContent !== String(value)) element.textContent = value;
}

async function requestJSON(path, { method = "GET", body, signal, timeout = 7000 } = {}) {
  const abort = new AbortController();
  const cancel = () => abort.abort();
  if (signal?.aborted) cancel();
  signal?.addEventListener("abort", cancel, { once: true });
  pendingRequests.add(abort);
  const timer = setTimeout(cancel, timeout);
  try {
    const response = await fetch(`/api${path}`, {
      method, headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body), signal: abort.signal,
    });
    const data = await response.json();
    if (!response.ok || data.error) {
      const error = new Error(data.error || `API error ${response.status}`);
      error.status = response.status;
      error.code = data.error_code;
      throw error;
    }
    return data;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
    pendingRequests.delete(abort);
  }
}

function friendlyError(error) {
  if (error.code === "reply_language_unavailable") return t("The model could not use the requested language. Try a multilingual model.");
  if (error.name === "AbortError") return t("The request timed out. The action may still be running; check KIRA before trying it again.");
  if (error.status === 503 || /fetch|network|backend not available/i.test(error.message)) {
    return t("KIRA’s backend is unavailable. Start the desktop app or run python launch_web.py on your computer, then try again.");
  }
  return error.message || t("Unable to complete this request.");
}
function notify(message) {
  writeText("toast", message);
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 4500);
}

/* Conversation messages are text, never executable HTML from the model/API. */
function addMessage(sender, text, isUser = false, historic = false) {
  messageSequence++;
  const block = document.createElement("article");
  block.className = `message-block${isUser ? " user-block" : sender === "SYSTEM" ? " system-block" : ""}`;
  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.innerHTML = `<svg class="icon" aria-hidden="true"><use href="#${isUser ? "i-user" : sender === "SYSTEM" ? "i-terminal" : "i-kira"}" /></svg>`;
  const content = document.createElement("div");
  content.className = "message-content";
  const meta = document.createElement("div");
  meta.className = "message-meta";
  const name = document.createElement("span");
  name.textContent = t(sender);
  name.dataset.sender = sender;
  const time = document.createElement("time");
  time.textContent = historic ? t("HISTORY") : new Date().toTimeString().slice(0, 8);
  if (!historic) time.dateTime = new Date().toISOString();
  const message = document.createElement("p");
  message.className = "message";
  message.textContent = String(text);
  message.setAttribute("dir", "auto");
  meta.append(name, time);
  content.append(meta, message);
  block.append(avatar, content);
  $("conversation").appendChild(block);
  // Bound the live DOM. Saved conversation history is not modified.
  if ($("conversation").children.length > 100) $("conversation").firstElementChild.remove();
  $("conversation").scrollTop = $("conversation").scrollHeight;
  $("conversation-empty").hidden = true;
  return block;
}

function setActivity(state) {
  if (state === "READY") state = commandPending ? "THINKING" : speechState !== "READY" ? speechState : "READY";
  activityState = state;
  writeText("activity", t(state));
  $("activity-dot").className = `activity-dot ${state === "THINKING" ? "thinking" : state === "SPEAKING" ? "speaking" : state === "READY" ? "active" : ""}`;
  $("hologram").dataset.activity = state.toLowerCase();
  const labels = { THINKING: t("PROCESSING YOUR REQUEST"), SPEAKING: t("VOICE CHANNEL ACTIVE"), LISTENING: t("LISTENING TO OPERATOR"), ERROR: t("CHECK SYSTEM CONNECTION") };
  document.querySelector(".stage-status-detail").textContent = labels[state] || t("AWAITING YOUR COMMAND");
}

const speech = new SpeechPlayer({
  fetchAudio: (text, { signal, language }) => requestJSON("/tts", { method: "POST", body: { text, language }, signal, timeout: 15000 }),
  onState: (state) => {
    speechState = state; setActivity(state);
    if (state === "SPEAKING") { sessionActivity.voice = true; updateAgentActivity(); }
  },
  onNotice: (code, details) => {
    if (code === "voice-unavailable") notify(t("No voice is available for {language}. The written reply is kept. Check Edge TTS or install a matching system voice.", { language: languageInfo(details.language).native_name }));
  },
});
speech.setEnabled(speechEnabled);
const hologram = new Hologram(document);
function speak(text, language = activeLocale()) { return speech.speak(text, { language: speechLocale(language) }); }
function stopSpeaking() { speech.stop(); hologram.mouth.reset(); lipDemoStarted = -Infinity; }

function updateVoiceControls() {
  const name = speechEnabled ? "i-volume" : "i-muted";
  $("mute").innerHTML = `<svg class="icon" aria-hidden="true"><use href="#${name}" /></svg>`;
  $("mute").setAttribute("aria-pressed", String(!speechEnabled));
  $("mute").setAttribute("aria-label", speechEnabled ? t("Mute voice output") : t("Enable voice output"));
  $("mute").title = speechEnabled ? t("Mute voice output") : t("Enable voice output");
  writeText("deck-voice-state", speechEnabled ? t("ENABLED") : t("MUTED"));
  writeText("voice-output", speechEnabled ? t("ENABLED") : t("MUTED"));
  writeText("settings-voice", speechEnabled ? t("VOICE: ON") : t("VOICE: OFF"));
  $("deck-voice").setAttribute("aria-pressed", String(speechEnabled));
  $("deck-voice").querySelector(".button-light").classList.toggle("off", !speechEnabled);
  $("voice-test").disabled = !speechEnabled;
  $("voice-test").title = speechEnabled ? t("Test KIRA’s voice") : t("Enable voice output in Settings first");
}
function toggleVoice() {
  speechEnabled = !speechEnabled;
  speech.setEnabled(speechEnabled);
  if (speechEnabled) speech.unlock();
  else { hologram.mouth.reset(); lipDemoStarted = -Infinity; }
  savePreference("kira.voice", speechEnabled ? "on" : "off");
  updateVoiceControls();
}
["mute", "deck-voice", "settings-voice"].forEach((id) => $(id).addEventListener("click", toggleVoice));
updateVoiceControls();

function motionDisabled() {
  return motionPreference === "off" || (motionPreference === "auto" && reducedMotion.matches);
}
function updateMotionButton() {
  document.documentElement.dataset.motion = motionPreference;
  writeText("motion-toggle", t("MOTION: {mode}", { mode: t(motionPreference.toUpperCase()) }));
  writeText("deck-motion-state", t("MOTION: {mode}", { mode: t(motionPreference.toUpperCase()) }));
  $("motion-toggle").title = t("Auto follows system reduced motion. On explicitly enables movement. Off keeps the projection still.");
  $("deck-motion").querySelector(".button-light").classList.toggle("off", motionDisabled());
  if (motionDisabled()) { hologram.mouth.reset(); lipDemoStarted = -Infinity; }
}
function cycleMotion() {
  const choices = ["auto", "on", "off"];
  motionPreference = choices[(choices.indexOf(motionPreference) + 1) % choices.length];
  savePreference("kira.motion", motionPreference);
  updateMotionButton();
}
$("motion-toggle").addEventListener("click", cycleMotion);
$("deck-motion").addEventListener("click", cycleMotion);
reducedMotion.addEventListener?.("change", updateMotionButton);
$("motion-test").addEventListener("click", () => {
  if (motionDisabled()) {
    writeText("diagnostic-status", t("Motion is disabled. Select Motion: On in Settings to test it."));
    return;
  }
  motionDemoStarted = performance.now();
  $("system-dialog").close();
  notify(t("Testing the holographic field · 3 seconds · no audio"));
});
function updateLipsButton() {
  writeText("lips-toggle", lipsEnabled ? t("LIPS: ON") : t("LIPS: OFF"));
  $("lips-toggle").setAttribute("aria-pressed", String(lipsEnabled));
}
$("lips-toggle").addEventListener("click", () => {
  lipsEnabled = !lipsEnabled;
  savePreference("kira.lips", lipsEnabled ? "on" : "off");
  if (!lipsEnabled) { hologram.mouth.reset(); lipDemoStarted = -Infinity; }
  updateLipsButton();
});
$("lip-test").addEventListener("click", () => {
  if (motionDisabled() || !lipsEnabled) {
    notify(t("Enable Motion: On and Lips: On in Settings to test the mouth."));
    return;
  }
  stopSpeaking();
  lipDemoStarted = performance.now();
  $("system-dialog").close();
  notify(t("Testing lip shapes · 4 seconds · no audio or desktop command"));
});
updateLipsButton();
$("voice-test").addEventListener("click", () => {
  if (!speech.enabled) return;
  speech.unlock();
  $("system-dialog").close();
  lipDemoStarted = -Infinity;
  const info = languageInfo(effectiveReplyLanguage());
  speak(VOICE_SAMPLES[info.code] || info.native_name, info.locale);
});
updateMotionButton();

function animate(now = performance.now()) {
  if (destroyed) return;
  animationId = requestAnimationFrame(animate);
  // CSS handles the slow ambient orbits; audio cues only need 30 updates/second.
  if (document.hidden || now - lastFrame < 1000 / 30) return;
  lastFrame = now;
  const voice = speech.motion.sample(now);
  const disabled = motionDisabled();
  const demoAge = (now - motionDemoStarted) / 1000;
  const demo = demoAge >= 0 && demoAge < 3;
  const demoEnergy = demo ? Math.sin(demoAge * Math.PI / 3) * (0.35 + 0.6 * Math.sin(demoAge * 9) ** 2) : null;
  const lipDemo = lipDemoPose((now - lipDemoStarted) / 1000);
  const projection = hologram.update(voice, { disabled, demoEnergy, time: now / 1000, lipsEnabled, lipDemo });
  const rendererState = hologram.mouth.renderer.state;
  const lipLabel = disabled ? t("LIP SYNC · MOTION DISABLED")
    : !lipsEnabled ? t("LIP SYNC · OFF")
    : hologram.mouth.renderer.canvas && ["unsupported", "unavailable"].includes(rendererState) ? t("LIP SYNC · RENDERER UNAVAILABLE")
    : rendererState === "loading" ? t("LIP SYNC · LOADING PORTRAIT")
    : lipDemo ? t("LIP SYNC · VISUAL TEST / NO AUDIO")
    : !voice.active ? t("LIP SYNC · IDLE")
    : projection.mouth.source === "word-timings" ? t("LIP SYNC · TTS WORD TIMING / ESTIMATED SHAPES")
    : projection.mouth.source === "word-events" ? t("LIP SYNC · BROWSER WORD TIMING / ESTIMATED SHAPES")
    : t("LIP SYNC · ESTIMATED TIMING");
  writeText("lip-status", lipLabel);
  $("voice-level").style.transform = `scaleX(${voice.energy.toFixed(3)})`;
  const label = disabled ? (motionPreference === "auto" ? t("MOTION OFF · SYSTEM SETTING") : t("MOTION OFF"))
    : demo ? t("TEST MOTION · NO AUDIO")
    : !speech.enabled ? t("VOICE MUTED")
    : !voice.active ? (speechState === "THINKING" ? t("WAITING FOR VOICE") : t("VOICE IDLE"))
    : voice.source === "audio" ? (voice.energy > 0.015 ? t("VOICE SYNC · AUDIO") : t("VOICE SYNC · QUIET / NO SIGNAL"))
    : voice.source === "words" ? t("VOICE SYNC · WORD TIMING") : t("VOICE SYNC · ESTIMATED");
  writeText("motion-status", label);
  writeText("diagnostic-status", label);
}

async function sendCommand(text, { shortcut = false } = {}) {
  text = String(text).trim();
  if (!text || commandPending || destroyed) return;
  commandPending = true;
  clearTimeout(errorTimer);
  stopSpeaking();
  speech.unlock(); // Unlock Web Audio during the user's gesture, before the reply.
  addMessage("OPERATOR", text, true);
  setActivity("THINKING");
  $("send").disabled = true;
  $("command-form").setAttribute("aria-busy", "true");
  commandCount++;
  writeText("command-count", String(commandCount).padStart(3, "0"));
  sessionActivity.commands++;
  const lowered = text.toLowerCase();
  if (/\b(search|cherche|recherche|find|trouve|locate)\b/.test(lowered)) sessionActivity.searches++;
  if (/\b(open|ouvre|launch|lance)\b/.test(lowered)) sessionActivity.opens++;
  updateAgentActivity();
  const thinking = addMessage("KIRA", t("Processing your request…"));
  thinking.classList.add("thinking");
  void delegateFor; // Agent registry kept for future re-introduction.

  const started = performance.now();
  try {
    const revision = languageRevision;
    const requestLanguage = shortcut && replyPreference === "auto" ? effectiveReplyLanguage() : replyPreference;
    const data = await requestJSON("/command", { method: "POST", body: {
      text, reply_language: requestLanguage, previous_language: lastReplyLanguage, interface_language: i18n.language,
    }, timeout: 120000 });
    if (destroyed) return;
    thinking.remove();
    if (data.language && /^[a-z]{2,3}$/.test(data.language)) {
      lastReplyLanguage = data.language;
      hasReplyLanguage = true;
      savePreference("kira.lastReplyLanguage", lastReplyLanguage);
    }
    if (data.reply_language_preference && revision === languageRevision
      && (data.reply_language_preference === "auto" || /^[a-z]{2,3}$/.test(data.reply_language_preference))) {
      replyPreference = data.reply_language_preference;
      savePreference("kira.replyLanguage", replyPreference);
      languageRevision++;
    }
    updateLanguageControls();
    writeText("response-time", `${((performance.now() - started) / 1000).toFixed(2)} s`);
    // Failed actions must never be labelled as successfully executed.
    const response = data.success === false ? t("KIRA could not complete: {action}.", { action: data.action || t("this action") }) + (data.response ? `\n${t("Backend response: {response}", { response: data.response })}` : "")
      : data.response || data.details || (data.action && data.action !== "none" ? t("Done: {action}", { action: data.action.replace(/_/g, " ") }) : t("Command received."));
    addMessage(data.success === false ? "SYSTEM" : "KIRA", response);
    if (data.success !== false && !data.language_warning) speak(response, data.locale || languageInfo(data.language || effectiveReplyLanguage()).locale);
    if (data.language_warning) notify(t("The model could not use the requested language. Try a multilingual model."));
  } catch (error) {
    if (destroyed) return;
    thinking.remove();
    addMessage("SYSTEM", friendlyError(error));
    setActivity("ERROR");
    errorTimer = setTimeout(() => setActivity("READY"), 4000);
  } finally {
    commandPending = false;
    $("send").disabled = false;
    $("command-form").setAttribute("aria-busy", "false");
    if (!destroyed) {
      if (activityState !== "ERROR") setActivity("READY");
      updateTasks();
    }
  }
}

$("command-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("command").value;
  if (!text.trim() || commandPending) return;
  $("command").value = "";
  sendCommand(text);
});
window.quickCmd = (command) => sendCommand(command, { shortcut: true }); // Retain compatibility with desktop integrations.
document.querySelectorAll("[data-command]").forEach((button) => button.addEventListener("click", () => {
  if (commandPending) return notify(t("KIRA is still processing your previous command."));
  sendCommand(button.dataset.command, { shortcut: true });
}));
document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => {
  $("command").value = button.dataset.prompt;
  $("command").focus();
  $("command").scrollIntoView({ block: "nearest" });
}));
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    $("system-dialog").close();
    $("command").focus();
  }
});
document.querySelectorAll(".command-navbar .nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".command-navbar .nav-item").forEach((other) => other.classList.remove("active"));
    item.classList.add("active");
  });
});
$("nav-kira").addEventListener("click", () => $("mic").click());
$("nav-home").addEventListener("click", () => { $("command").focus(); });
$("nav-conv").addEventListener("click", () => { $("command").focus(); });
$("nav-agents").addEventListener("click", () => {
  const panel = document.querySelector(".agents-panel");
  panel.scrollIntoView({ block: "nearest" });
  panel.classList.remove("flash");
  requestAnimationFrame(() => panel.classList.add("flash"));
});
$("nav-history").addEventListener("click", () => {
  const feed = $("conversation");
  feed.scrollIntoView({ block: "nearest" });
  feed.scrollTop = 0;
  feed.classList.remove("flash");
  requestAnimationFrame(() => feed.classList.add("flash"));
});
$("nav-bell").addEventListener("click", () => openPanel("diagnostics"));
$("nav-gear").addEventListener("click", () => openPanel("settings"));
$("nav-tools").addEventListener("click", () => openPanel("diagnostics"));
$("nav-settings").addEventListener("click", () => openPanel("settings"));
$("nav-power").addEventListener("click", () => notify(t("KIRA runs locally on this computer. Close the window to shut it down.")));
// The AGENTS panel is optional in the layout; keep the handler when present.
const addAgent = $("add-agent");
if (addAgent) addAgent.addEventListener("click", () => notify(t("KIRA modules are built in. Pick one to fill the command line.")));

$("clear-chat").addEventListener("click", () => {
  if (commandPending) return notify(t("Wait for the current command to finish before clearing the view."));
  $("conversation").replaceChildren();
  addMessage("KIRA", t("Channel cleared.\nReady for your next command, Operator."));
  $("conversation-empty").hidden = false;
  notify(t("Conversation view cleared. Saved history is unchanged."));
});

/* Browser voice input; the projection reacts to OUTPUT, not microphone audio. */
$("voice-language").value = voiceLanguage;
$("voice-language").addEventListener("change", () => {
  voiceLanguage = $("voice-language").value;
  savePreference("kira.language", voiceLanguage);
  if (recognition) {
    if (listening) recognition.stop();
    recognition.lang = listeningLocale();
  }
});
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (Recognition) {
  recognition = new Recognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = listeningLocale();
  recognition.onstart = () => {
    listening = true;
    stopSpeaking();
    $("mic").classList.add("listening");
    $("nav-kira").classList.add("listening");
    $("mic").setAttribute("aria-label", t("Stop voice input"));
    setActivity("LISTENING");
  };
  recognition.onresult = (event) => {
    const text = event.results[0][0].transcript;
    $("command").value = text;
    if (!commandPending) { $("command").value = ""; sendCommand(text); }
  };
  recognition.onend = () => {
    listening = false;
    $("mic").classList.remove("listening");
    $("nav-kira").classList.remove("listening");
    $("mic").setAttribute("aria-label", t("Start voice input"));
    setActivity("READY");
  };
  recognition.onerror = (event) => {
    if (event.error === "aborted") return;
    notify(event.error === "not-allowed" ? t("Microphone access was denied. Allow it in your browser settings, or type a command.")
      : event.error === "no-speech" ? t("No speech detected. Try again, or type a command.")
      : t("Voice input is unavailable. You can still type a command."));
  };
  $("mic").addEventListener("click", () => {
    if (commandPending) return notify(t("Wait for KIRA to finish processing before using voice input."));
    try { speech.unlock(); recognition.lang = listeningLocale(); listening ? recognition.stop() : recognition.start(); }
    catch { notify(t("Voice input is already starting. Please wait a moment.")); }
  });
} else {
  $("mic").disabled = true;
  $("mic").title = t("Speech recognition is unavailable in this browser. Type a command instead.");
}

function updateClock() {
  const now = new Date();
  writeText("clock-time", now.toLocaleTimeString(i18n.language, { hour12: false }));
  writeText("clock-date", now.toLocaleDateString(i18n.language, { weekday: "short", day: "2-digit", month: "short", year: "numeric" }).toUpperCase());
  const seconds = Math.floor((performance.now() - startedAt) / 1000);
  writeText("uptime", [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60].map((n) => String(n).padStart(2, "0")).join(":"));
}
$("boot-time").textContent = new Date().toTimeString().slice(0, 8);
writeText("transport", window.location.protocol === "https:" ? "HTTPS" : "HTTP / LOCAL");
updateClock();

let statusPending = false;
async function updateStatus() {
  if (statusPending || commandPending || destroyed || document.hidden) return;
  statusPending = true;
  const started = performance.now();
  try {
    const data = await requestJSON("/status");
    const available = data.backend_available ?? Boolean(data.model && data.model !== "unknown");
    writeText("latency", `${Math.round(performance.now() - started)} ms`);
    writeText("model-name", data.model && data.model !== "unknown" ? data.model : t("NOT LOADED"));
    $("model-name").title = data.model || t("No neural engine loaded");
    writeText("neural-status", available ? t("ACTIVE") : t("STANDBY"));
    writeText("backend-state", available ? t("CONNECTED") : t("NOT LOADED"));
    writeText("status-text", available ? t("NEURAL LINK ACTIVE") : t("INTERFACE PREVIEW"));
    $("connection-pill").classList.toggle("connected", available);
    writeText("diagnostic-connection", available ? t("Connected to local KIRA") : t("API online · command engine not loaded"));
  } catch {
    writeText("latency", "—");
    writeText("model-name", t("UNAVAILABLE"));
    writeText("neural-status", t("OFFLINE"));
    writeText("backend-state", t("OFFLINE"));
    writeText("status-text", t("BACKEND OFFLINE"));
    $("connection-pill").classList.remove("connected");
    writeText("diagnostic-connection", t("Offline · start the KIRA launcher"));
  } finally { statusPending = false; }
}

let telemetryPending = false;
async function updateTelemetry() {
  if (telemetryPending || commandPending || destroyed || document.hidden) return;
  telemetryPending = true;
  const paint = (key, value) => {
    const valid = typeof value === "number" && Number.isFinite(value);
    const percent = valid ? Math.max(0, Math.min(100, value)) : 0;
    writeText(key, valid ? `${percent.toFixed(1)}%` : "—");
    $(`${key}-bar`).style.width = `${percent}%`;
    const gauge = $(`gauge-${key}`);
    if (gauge) gauge.style.strokeDashoffset = valid ? String((100 - percent) / 100 * 125.7) : "125.7";
  };
  try {
    const data = await requestJSON("/system");
    paint("cpu", data.cpu_percent);
    paint("memory", data.memory_percent);
    paint("disk", data.disk_percent);
    sessionActivity.cpu = typeof data.cpu_percent === "number" ? data.cpu_percent : null;
    sessionActivity.memory = typeof data.memory_percent === "number" ? data.memory_percent : null;
    for (const key of ["cpu", "memory", "disk"]) {
      const value = key === "cpu" ? data.cpu_percent : key === "memory" ? data.memory_percent : data.disk_percent;
      sparkData[key].push(typeof value === "number" ? value : 0);
      if (sparkData[key].length > 24) sparkData[key].shift();
      drawSpark(key);
    }
    updateAgentActivity();
    const sub = (key, value) => writeText(`gauge-sub-${key}`, value);
    sub("cpu", typeof data.cpu_freq_mhz === "number" ? `${(data.cpu_freq_mhz / 1000).toFixed(2)} GHz` : "—");
    sub("memory", typeof data.memory_used_gb === "number" && typeof data.memory_total_gb === "number"
      ? `${data.memory_used_gb} / ${data.memory_total_gb} GB` : "—");
    sub("disk", typeof data.disk_used_gb === "number" && typeof data.disk_total_gb === "number"
      ? `${data.disk_used_gb} / ${data.disk_total_gb} GB` : "—");
    const down = typeof data.net_down_mbps === "number" ? data.net_down_mbps : null;
    const up = typeof data.net_up_mbps === "number" ? data.net_up_mbps : null;
    const rate = (v) => (v >= 10 ? Math.round(v) : Math.round(v * 10) / 10);
    writeText("network", up !== null ? `\u2191 ${rate(up)}` : down !== null ? `\u2193 ${rate(down)}` : "—");
    writeText("gauge-sub-network", down !== null || up !== null ? `\u2193 ${down ?? "—"} \u00b7 \u2191 ${up ?? "—"} Mb/s` : "—");
    const gaugeNetwork = $("gauge-network");
    if (gaugeNetwork) {
      const net = down !== null ? Math.min(100, down * 2) : 0;
      gaugeNetwork.style.strokeDashoffset = String((100 - net) / 100 * 125.7);
    }
    sparkData.network.push(down ?? 0);
    if (sparkData.network.length > 24) sparkData.network.shift();
    drawSpark("network");
    const parts = [`${commandCount} ${t("commands")}`, `${sessionActivity.searches} ${t("searches")}`,
      `${sessionActivity.opens} ${t("opens")}`, `${sessionActivity.tasks} ${t("pending tasks")}`];
    writeText("agent-activity-summary", parts.join(" · "));
    const cpuNow = typeof data.cpu_percent === "number" ? Math.round(data.cpu_percent) : null;
    const memNow = typeof data.memory_percent === "number" ? Math.round(data.memory_percent) : null;
    writeText("agent-sub-system", cpuNow !== null ? `CPU ${cpuNow}% · RAM ${memNow}%` : "—");
    writeText("agent-sub-data", typeof data.memory_used_gb === "number"
      ? `${data.memory_used_gb} / ${data.memory_total_gb} GB` : "—");
    writeText("agent-sub-research", `${sessionActivity.searches} ${t("searches")}`);
    writeText("agent-sub-web", `${sessionActivity.opens} ${t("opens")}`);
    writeText("agent-sub-content", sessionActivity.voice ? t("ACTIVE") : t("STANDBY"));
    writeText("agent-sub-automation", `${sessionActivity.tasks} ${t("pending tasks")}`);
    writeText("gpu", data.gpu || t("UNAVAILABLE"));
    writeText("cpu-temp", typeof data.cpu_temp_c === "number" ? `${Math.round(data.cpu_temp_c)}\u00b0C` : "\u2014");
    $("gpu").title = data.gpu || t("Graphics telemetry is unavailable");
    writeText("telemetry-live", t("LIVE"));
    $("telemetry-live").classList.add("live");
  } catch {
    ["cpu", "memory", "disk"].forEach((key) => paint(key, null));
    writeText("gpu", t("UNAVAILABLE"));
    writeText("cpu-temp", "\u2014");
    writeText("telemetry-live", t("OFFLINE"));
    $("telemetry-live").classList.remove("live");
    sessionActivity.cpu = null;
    sessionActivity.memory = null;
    updateAgentActivity();
    ["cpu", "memory", "disk"].forEach((key) => writeText(`gauge-sub-${key}`, "—"));
    writeText("network", "—");
    writeText("gauge-sub-network", "—");
    writeText("agent-activity-summary", "—");
    for (const key of ["cpu", "memory", "disk", "network"]) { sparkData[key].length = 0; drawSpark(key); }
  } finally { telemetryPending = false; }
}

let tasksPending = false;
async function updateTasks() {
  if (tasksPending || destroyed || commandPending) return;
  tasksPending = true;
  try {
    const data = await requestJSON("/tasks?type=todo&completed=false");
    const tasks = Array.isArray(data.tasks) ? data.tasks : [];
    writeText("task-count", tasks.length);
    sessionActivity.tasks = tasks.length;
    updateAgentActivity();
    renderRecentTasks(tasks);
    $("tasks-list").replaceChildren();
    if (!tasks.length) {
      const empty = document.createElement("p");
      empty.className = "task-empty";
      empty.textContent = t("All clear. No pending tasks.\nAdd a task below, or ask KIRA to remember it.");
      $("tasks-list").appendChild(empty);
    }
    tasks.forEach((task) => {
      const row = document.createElement("div");
      row.className = "task-item";
      const complete = document.createElement("button");
      complete.type = "button";
      complete.title = t("Mark complete");
      complete.setAttribute("aria-label", t("Complete task: {title}", { title: task.title }));
      complete.textContent = "✓";
      complete.addEventListener("click", async () => {
        complete.disabled = true;
        try {
          const result = await requestJSON("/task/complete", { method: "POST", body: { id: task.id } });
          if (!result.success) throw new Error(t("The task could not be completed."));
          writeText("task-feedback", t("Task completed."));
          await updateTasks();
        } catch (error) { complete.disabled = false; writeText("task-feedback", friendlyError(error)); }
      });
      const title = document.createElement("span");
      title.textContent = task.title;
      row.append(complete, title);
      $("tasks-list").appendChild(row);
    });
  } catch {
    writeText("task-count", "—");
    $("tasks-list").replaceChildren();
    const empty = document.createElement("p");
    empty.className = "task-empty";
    empty.textContent = t("Task manager unavailable. Start KIRA’s backend to access your tasks.");
    $("tasks-list").appendChild(empty);
    renderRecentTasks([]);
  } finally { tasksPending = false; }
}
$("task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = $("task-title").value.trim();
  const button = $("task-form").querySelector("button");
  if (!title || button.disabled) return;
  button.disabled = true;
  writeText("task-feedback", t("Saving…"));
  try {
    await requestJSON("/task", { method: "POST", body: { title, type: "todo" } });
    $("task-title").value = "";
    writeText("task-feedback", t("Task saved to local memory."));
    await updateTasks();
  } catch (error) { writeText("task-feedback", friendlyError(error)); }
  finally { button.disabled = false; }
});

async function loadHistory() {
  try {
    const sequence = messageSequence;
    const data = await requestJSON("/history?limit=20");
    if (messageSequence !== sequence || !Array.isArray(data.messages) || !data.messages.length) return;
    $("conversation").replaceChildren();
    data.messages.forEach((message) => {
      if (message.role !== "user" && message.role !== "assistant") return;
      addMessage(message.role === "user" ? "OPERATOR" : "KIRA", message.content, message.role === "user", true);
    });
  } catch { /* Fresh/offline instances keep the genuine startup greeting. */ }
}

/* Dialog is native: focus is trapped, Escape works, and focus is restored. */
function openPanel(name) {
  const titles = { settings: t("INTERFACE SETTINGS"), diagnostics: t("SYSTEM DIAGNOSTICS"), tasks: t("YOUR WORKSPACE") };
  if (!titles[name]) return;
  currentPanel = name;
  ["settings", "diagnostics", "tasks"].forEach((panel) => { $(`${panel}-panel`).hidden = panel !== name; });
  writeText("dialog-title", titles[name]);
  if (!$("system-dialog").open) $("system-dialog").showModal();
  if (name === "tasks") updateTasks();
  if (name === "diagnostics") updateStatus();
}
document.querySelectorAll("[data-dialog]").forEach((button) => button.addEventListener("click", () => openPanel(button.dataset.dialog)));

// Agent modules are rendered from the ui/agents.mjs registry: adding an
// agent later means adding one configuration entry, not new UI code.
function wireAgentButton(button) {
  if (button.dataset.command) button.addEventListener("click", () => {
    if (commandPending) return notify(t("KIRA is still processing your previous command."));
    sendCommand(button.dataset.command, { shortcut: true });
  });
  if (button.dataset.prompt) button.addEventListener("click", () => {
    $("command").value = button.dataset.prompt;
    $("command").focus();
    $("command").scrollIntoView({ block: "nearest" });
  });
  if (button.dataset.dialog) button.addEventListener("click", () => openPanel(button.dataset.dialog));
}

const agentRows = new Map();

function renderAgents() {
  const list = $("agents-list");
  const cards = document.querySelector(".agent-cards");
  const meters = $("agent-meters");
  if (!list || !meters) return;
  agentRows.clear();
  if (cards) cards.replaceChildren();
  list.replaceChildren(); meters.replaceChildren();
  for (const agent of AGENTS) {
    const attrs = agent.action.prompt ? `data-prompt="${agent.action.prompt}"`
      : agent.action.command ? `data-command="${agent.action.command}"`
      : `data-dialog="${agent.action.dialog}"`;
    const row = document.createElement("button");
    row.type = "button"; row.className = "agent-row"; row.setAttribute("attrs", "");
    row.innerHTML = `<b class="chev">›</b><span class="agent-ico"><svg class="icon"><use href="#${agent.icon}" /></svg></span><span class="agent-id"><b>${t(agent.name)}</b><small>${t(agent.description)}</small></span><span class="agent-state"><i class="online-dot"></i><span>${t("ONLINE")}</span></span>`;
    Object.entries(agent.action).forEach(([k, v]) => { row.dataset[k] = v; });
    agentRows.set(agent.id, row);
    list.appendChild(row); wireAgentButton(row);

    if (cards) {
      const chip = document.createElement("button");
      chip.type = "button"; chip.className = `agent-chip chip-${agent.chip}`;
      const chipAction = agent.chipAction || agent.action;
      Object.entries(chipAction).forEach(([k, v]) => { chip.dataset[k] = v; });
      chip.innerHTML = `<span class="agent-ico"><svg class="icon"><use href="#${agent.icon}" /></svg></span><span>${t(agent.name)}</span>`;
      cards.appendChild(chip); wireAgentButton(chip);
    }

    const meter = document.createElement("div");
    meter.className = "agent-meter-row";
    meter.innerHTML = `<span class="agent-who"><svg class="icon"><use href="#${agent.icon}" /></svg><span class="agent-who-text"><b>${t(agent.name)}</b><small id="agent-sub-${agent.id}">—</small></span></span><div class="agent-meter"><span id="agent-bar-${agent.id}"></span></div><strong id="agent-val-${agent.id}">—</strong>`;
    meters.appendChild(meter);
  }
  drawAgentLinks();
  updateAgentActivity();
}

function drawAgentLinks() {
  const stage = $(".hologram") || document.querySelector(".hologram");
  const svg = $("agent-links");
  if (!stage || !svg || typeof stage.getBoundingClientRect !== "function") return;
  const box = stage.getBoundingClientRect();
  if (!box || !box.width) return;
  svg.setAttribute("viewBox", `0 0 ${Math.round(box.width)} ${Math.round(box.height)}`);
  svg.replaceChildren();
  const cx = box.width / 2, cy = box.height * 0.42;
  for (const agent of AGENTS) {
    const chip = document.querySelector(`.agent-chip.chip-${agent.chip}`);
    if (!chip) continue;
    const b = chip.getBoundingClientRect();
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", cx); line.setAttribute("y1", cy);
    line.setAttribute("x2", b.left - box.left + b.width / 2);
    line.setAttribute("y2", b.top - box.top + b.height / 2);
    line.classList.add("agent-link");
    line.dataset.agent = agent.id;
    svg.appendChild(line);
    const node = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    node.setAttribute("cx", b.left - box.left + b.width / 2);
    node.setAttribute("cy", b.top - box.top + b.height / 2);
    node.setAttribute("r", 2.4);
    node.classList.add("agent-node");
    svg.appendChild(node);
  }
}
window.addEventListener("resize", drawAgentLinks);
window.addEventListener("load", drawAgentLinks);
document.querySelectorAll("[data-topnav]").forEach((button) => button.addEventListener("click", () => {
  const target = $(button.dataset.topnav);
  if (target) target.click();
}));
const telemetryCollapse = $("telemetry-collapse");
if (telemetryCollapse) telemetryCollapse.addEventListener("click", () => {
  const panel = telemetryCollapse.closest(".telemetry-panel") || document.querySelector(".telemetry-panel");
  if (!panel) return;
  const collapsed = panel.classList.toggle("collapsed");
  telemetryCollapse.setAttribute("aria-expanded", collapsed ? "false" : "true");
});
renderAgents();
$("close-dialog").addEventListener("click", () => $("system-dialog").close());
$("system-dialog").addEventListener("click", (event) => {
  if (event.target !== $("system-dialog")) return;
  const box = $("system-dialog").getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) $("system-dialog").close();
});
$("fullscreen").addEventListener("click", async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen();
    else notify(t("Use your window’s maximize button for a full-screen cockpit."));
  } catch { notify(t("Fullscreen is unavailable here. Open KIRA in its own window to use it.")); }
});
document.addEventListener("fullscreenchange", () => {
  $("fullscreen").title = document.fullscreenElement ? t("Exit fullscreen") : t("Enter fullscreen");
});

$("interface-language").addEventListener("change", () => {
  i18n.setLanguage($("interface-language").value);
  savePreference("kira.uiLanguage", i18n.language);
  if (!hasReplyLanguage && replyPreference === "auto") lastReplyLanguage = i18n.language;
  i18n.apply(document);
  for (const node of document.querySelectorAll("[data-sender]")) node.textContent = t(node.dataset.sender);
  updateLanguageControls(); updateVoiceControls(); updateMotionButton(); updateLipsButton();
  setActivity(activityState); updateClock();
  $("mic").setAttribute("aria-label", t(listening ? "Stop voice input" : "Start voice input"));
  if (!recognition) $("mic").title = t("Speech recognition is unavailable in this browser. Type a command instead.");
  if (currentPanel && $("system-dialog").open) openPanel(currentPanel);
  updateStatus(); updateTelemetry(); updateTasks();
});
$("reply-language").addEventListener("change", () => {
  replyPreference = $("reply-language").value || "auto";
  languageRevision++;
  savePreference("kira.replyLanguage", replyPreference);
  updateLanguageControls();
});
updateLanguageControls();
loadLanguageCatalog();

window.addEventListener("pagehide", () => {
  destroyed = true;
  cancelAnimationFrame(animationId);
  intervals.forEach(clearInterval);
  clearTimeout(toastTimer);
  clearTimeout(errorTimer);
  pendingRequests.forEach((request) => request.abort());
  reducedMotion.removeEventListener?.("change", updateMotionButton);
  recognition?.abort();
  speech.destroy();
  hologram.destroy();
});
// A back/forward-cache restore needs fresh timers and a new audio context.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) window.location.reload();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && !destroyed) { lastFrame = -Infinity; updateStatus(); updateTelemetry(); }
});
intervals.push(setInterval(updateClock, 1000), setInterval(updateTelemetry, 3000), setInterval(updateStatus, 10000), setInterval(() => {
  if (!document.hidden) updateTasks();
}, 8000));
updateStatus();
updateTelemetry();
updateTasks();
loadHistory();
animate();
