import { SpeechPlayer } from "../../ui/speech.mjs";

export function analyser(amplitude = 0, bass = 0, treble = 0) {
  return {
    fftSize: 1024, frequencyBinCount: 512, context: { sampleRate: 48000 },
    getByteTimeDomainData(out) {
      for (let i = 0; i < out.length; i++) out[i] = 128 + (i % 2 ? amplitude : -amplitude);
    },
    getByteFrequencyData(out) {
      for (let i = 0; i < out.length; i++) out[i] = i < 10 ? bass : treble;
    },
  };
}

export function playerRig(options = {}) {
  const audios = [], utterances = [], revoked = [], contexts = [], timers = new Map(), states = [], notices = [];
  let voices = options.voices || [{ lang: "en-US", name: "Zira" }];
  const voiceListeners = new Set();
  let serial = 0, now = 0, cancelled = 0;
  class Audio {
    constructor(url) { this.src = url; this.currentTime = 0; this.paused = true; audios.push(this); }
    play() {
      if (options.playReject) return Promise.reject(new Error("autoplay blocked"));
      this.paused = false;
      this.onplaying?.();
      return options.playPromise || Promise.resolve();
    }
    pause() { this.paused = true; this.onpause?.(); }
    removeAttribute() { this.src = ""; }
    load() { this.loaded = true; }
  }
  class AudioContext {
    constructor() {
      this.state = options.suspended ? "suspended" : "running";
      this.destination = {};
      this.nodes = [];
      contexts.push(this);
    }
    resume() { return options.suspended ? Promise.resolve() : (this.state = "running", Promise.resolve()); }
    createAnalyser() {
      if (options.graphFail) throw new Error("analyser unavailable");
      const node = { ...analyser(20, 100, 100), ...this.node() };
      this.nodes.push(node);
      return node;
    }
    createGain() {
      if (options.graphFail) throw new Error("gain unavailable");
      let level = 1;
      const schedule = [];
      const param = {
        get value() { return level; },
        set value(next) { level = next; },
        setValueAtTime(next, _when) { level = next; schedule.push("set"); },
        linearRampToValueAtTime(next, _when) { level = next; schedule.push("ramp"); },
        cancelScheduledValues(_when) { schedule.push("cancel"); },
      };
      const node = { gain: param, schedule, ...this.node() };
      this.nodes.push(node);
      return node;
    }
    node() { return { disconnected: false, connect() {}, disconnect() { this.disconnected = true; } }; }
    createMediaElementSource() { const node = this.node(); this.nodes.push(node); return node; }
    close() { this.state = "closed"; return Promise.resolve(); }
  }
  const env = {
    Audio, AudioContext: options.noContext ? undefined : AudioContext,
    AbortController, Blob, atob,
    performance: { now: () => now },
    setTimeout(fn, delay) { const id = ++serial; timers.set(id, { fn, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
    URL: { createObjectURL: () => `blob:voice-${++serial}`, revokeObjectURL: (url) => revoked.push(url) },
    SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
    speechSynthesis: options.noSynth ? undefined : {
      getVoices: () => voices,
      ...(options.delayedVoices ? { addEventListener: (event, listener) => voiceListeners.add(listener), removeEventListener: (event, listener) => voiceListeners.delete(listener) } : {}),
      speak(utterance) { utterances.push(utterance); if (!options.noStart) utterance.onstart?.(); },
      cancel() { cancelled++; utterances.at(-1)?.onend?.(); },
    },
  };
  const fetches = [];
  const player = new SpeechPlayer({
    env, onState: (state) => states.push(state), onNotice: (code, detail) => notices.push({ code, ...detail }),
    fetchAudio: (text, params) => {
      fetches.push({ text, ...params });
      return options.fetchAudio ? options.fetchAudio(text, params) : Promise.resolve({ audio: "YWJj" });
    },
  });
  return {
    player, env, audios, contexts, utterances, revoked, states, notices, timers, fetches, voiceListeners,
    setVoices(next) { voices = next; for (const listener of [...voiceListeners]) listener(); },
    get cancelled() { return cancelled; },
    advance(ms = 100) { now += ms; return { ...player.motion.sample() }; },
    fireTimers() { for (const [id, timer] of [...timers]) { timers.delete(id); timer.fn(); } },
  };
}

