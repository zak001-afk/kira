// Speech-driven motion, independent of Three.js. No microphone is sampled.
const clamp = (value, low = 0, high = 1) => Math.min(high, Math.max(low, value));

export function cleanForSpeech(text) {
  return String(text || "")
    .replace(/```[\s\S]*?```/g, "code block")
    .replace(/`[^`]+`/g, "")
    .replace(/https?:\/\/\S+/g, "link")
    .replace(/[*_~]/g, "")
    .trim();
}

// Web Speech doesn't expose its audio. Word boundaries anchor this estimated
// envelope; voices without boundary events use the same text-paced fallback.
function wordTimeline(text, rate = 1) {
  let start = 0;
  return Array.from(text.matchAll(/\S+/gu), (match) => {
    const duration = (110 + Math.min(match[0].length, 12) * 30) / rate;
    const word = { index: match.index, start, duration };
    start += duration + (/[.!?…]$/.test(match[0]) ? 260 : /[,;:]$/.test(match[0]) ? 120 : 35);
    return word;
  });
}

export class SpeechMotion {
  constructor(now = () => performance.now()) {
    this.now = now;
    this.frame = { energy: 0, low: 0, high: 0, active: false };
    this.last = now();
    this.stop();
  }

  stop() {
    this.mode = null;
    this.analyser = null;
    this.media = null;
    this.paused = false;
    this.words = [];
    this.offset = 0;
    // Keep the envelope: sample() releases it gently back to idle.
  }

  startAudio(analyser, media, text) {
    this.stop();
    this.mode = "audio";
    this.media = media;
    this.analyser = analyser;
    if (analyser) {
      this.wave = new Uint8Array(analyser.fftSize);
      this.bins = new Uint8Array(analyser.frequencyBinCount);
    }
    this.words = wordTimeline(text);
  }

  startBrowser(text, rate = 1) {
    this.stop();
    this.mode = "browser";
    this.started = this.now();
    this.words = wordTimeline(text, rate);
  }

  boundary(charIndex) {
    if (this.mode !== "browser" || !Number.isFinite(charIndex)) return;
    const word = this.words.findLast((item) => item.index <= charIndex);
    if (word) this.offset = word.start - (this.now() - this.started);
  }

  pause() {
    if (!this.paused) this.pausedAt = this.now();
    this.paused = true;
  }

  resume() {
    if (this.paused && this.mode === "browser") this.started += this.now() - this.pausedAt;
    this.paused = false;
  }

  estimatedEnergy(elapsed) {
    const word = this.words.findLast((item) => item.start <= elapsed);
    if (!word) return 0;
    const progress = (elapsed - word.start) / word.duration;
    // Silence between words/sentences; never a permanently-running oscillator.
    return progress >= 0 && progress < 1 ? Math.sin(progress * Math.PI) * 0.65 : 0;
  }

  sample(now = this.now()) {
    const dt = clamp((now - this.last) / 1000, 0, 0.1);
    this.last = now;
    let energy = 0, low = 0, high = 0;
    const active = Boolean(this.mode && !this.paused);
    if (active && this.analyser) {
      this.analyser.getByteTimeDomainData(this.wave);
      let squares = 0;
      for (const byte of this.wave) squares += ((byte - 128) / 128) ** 2;
      // RMS follows syllables; a noise floor keeps silence genuinely still.
      energy = clamp((Math.sqrt(squares / this.wave.length) - 0.008) * 6);
      this.analyser.getByteFrequencyData(this.bins);
      const hzPerBin = this.analyser.context.sampleRate / this.analyser.fftSize;
      const band = (from, to) => {
        const first = Math.max(1, Math.floor(from / hzPerBin));
        const end = Math.min(this.bins.length, Math.ceil(to / hzPerBin));
        let sum = 0;
        for (let i = first; i < end; i++) sum += this.bins[i];
        return end > first ? sum / ((end - first) * 255) : 0;
      };
      low = band(80, 450) * energy;
      high = band(1800, 6500) * energy;
    } else if (active) {
      // Without Web Audio, follow the media clock, not the request's start.
      const elapsed = this.mode === "audio"
        ? this.media.currentTime * 1000
        : now - this.started + this.offset;
      energy = this.estimatedEnergy(elapsed);
      low = energy * 0.45;
      high = energy * 0.3;
    }
    for (const [key, target] of [["energy", energy], ["low", low], ["high", high]]) {
      const smoothing = 1 - Math.exp(-dt / (target > this.frame[key] ? 0.045 : 0.16));
      this.frame[key] += (target - this.frame[key]) * smoothing;
      if (this.frame[key] < 0.0001) this.frame[key] = 0;
    }
    this.frame.active = active;
    return this.frame;
  }
}

export class SpeechPlayer {
  constructor({ fetchAudio, onState = () => {}, env = globalThis, motion } = {}) {
    this.env = env;
    this.fetchAudio = fetchAudio;
    this.onState = onState;
    this.motion = motion || new SpeechMotion(() => env.performance.now());
    this.enabled = true;
    this.session = null;
    this.context = null;
  }

  // Call during the user's click/keypress, before waiting for the AI reply.
  // If Web Audio is blocked, leave media playback on its normal output path.
  unlock() {
    try {
      const Context = this.env.AudioContext || this.env.webkitAudioContext;
      if (!this.context && Context) this.context = new Context();
      if (this.context?.state === "suspended") this.context.resume().catch(() => {});
    } catch { /* Web Audio is optional; speech must still be audible. */ }
  }

  isCurrent(session) {
    return this.enabled && this.session === session;
  }

  clearTimer(session) {
    this.env.clearTimeout(session.timer);
    session.timer = null;
  }

  releaseMedia(session) {
    const audio = session.audio;
    if (audio) {
      audio.onplaying = audio.onpause = audio.onwaiting = audio.onended = audio.onerror = null;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    session.source?.disconnect();
    session.analyser?.disconnect();
    if (session.url) this.env.URL.revokeObjectURL(session.url);
    session.audio = session.url = session.source = session.analyser = null;
  }

  finish(session) {
    if (this.session !== session) return;
    this.session = null; // invalidate callbacks before cancelling playback
    this.clearTimer(session);
    session.abort.abort();
    this.releaseMedia(session);
    if (session.utterance) this.env.speechSynthesis?.cancel();
    this.motion.stop();
    this.onState("READY");
  }

  stop() {
    if (this.session) this.finish(this.session);
    else this.motion.stop();
  }

  setEnabled(enabled) {
    this.enabled = enabled;
    if (!enabled) this.stop();
  }

  async speak(text) {
    this.stop();
    const cleanText = cleanForSpeech(text);
    if (!this.enabled || !cleanText) return;
    const session = { abort: new this.env.AbortController(), fallback: false };
    this.session = session;
    this.unlock();
    this.onState("THINKING");
    // Also handles a fetch implementation that never resolves after abort.
    session.timer = this.env.setTimeout(() => this.fallback(session, cleanText), 15000);
    try {
      const data = await this.fetchAudio(cleanText, { signal: session.abort.signal });
      if (!this.isCurrent(session) || session.fallback) return;
      this.clearTimer(session);
      if (data.error || !data.audio) throw new Error(data.error || "No speech audio");
      const bytes = Uint8Array.from(this.env.atob(data.audio), (char) => char.charCodeAt(0));
      session.url = this.env.URL.createObjectURL(new this.env.Blob([bytes], { type: "audio/mpeg" }));
      const audio = session.audio = new this.env.Audio(session.url);
      // Do not route audio into a suspended context: that would mute it.
      if (this.context?.state === "running") {
        try {
          session.analyser = this.context.createAnalyser();
          session.analyser.fftSize = 1024;
          session.analyser.smoothingTimeConstant = 0.55;
          session.source = this.context.createMediaElementSource(audio);
          session.source.connect(session.analyser);
          session.analyser.connect(this.context.destination);
        } catch {
          // If routing partially succeeded, restore an audible direct path.
          session.source?.disconnect();
          session.analyser?.disconnect();
          session.source?.connect(this.context.destination);
          session.analyser = null;
        }
      }
      audio.onplaying = () => {
        if (!this.isCurrent(session) || session.fallback) return;
        this.motion.startAudio(session.analyser, audio, cleanText);
        this.onState("SPEAKING");
      };
      const pause = () => {
        if (!this.isCurrent(session) || session.fallback) return;
        this.motion.pause();
        this.onState("THINKING");
      };
      audio.onpause = audio.onwaiting = pause;
      audio.onended = () => {
        if (!session.fallback) this.finish(session);
      };
      audio.onerror = () => this.fallback(session, cleanText);
      // A media decoder/autoplay operation can hang too.
      session.timer = this.env.setTimeout(() => this.fallback(session, cleanText), 15000);
      await audio.play();
      if (this.isCurrent(session) && !session.fallback) this.clearTimer(session);
    } catch {
      this.fallback(session, cleanText);
    }
  }

  fallback(session, text) {
    if (!this.isCurrent(session) || session.fallback) return;
    session.fallback = true;
    this.clearTimer(session);
    session.abort.abort();
    this.releaseMedia(session);
    this.motion.stop();
    const synth = this.env.speechSynthesis;
    if (!synth || !this.env.SpeechSynthesisUtterance) {
      this.finish(session);
      return;
    }
    try {
      const utterance = session.utterance = new this.env.SpeechSynthesisUtterance(text);
      utterance.rate = 0.95;
      utterance.pitch = 1.1;
      utterance.volume = 1;
      const voices = synth.getVoices();
      const voice = voices.find((v) => v.lang.startsWith("en") && /Female|Samantha|Zira/.test(v.name))
        || voices.find((v) => v.lang.startsWith("en"));
      if (voice) utterance.voice = voice;
      utterance.onstart = () => {
        if (!this.isCurrent(session)) return;
        this.clearTimer(session);
        this.motion.startBrowser(text, utterance.rate);
        this.onState("SPEAKING");
      };
      utterance.onboundary = (event) => {
        if (this.isCurrent(session) && (!event.name || event.name === "word")) this.motion.boundary(event.charIndex);
      };
      utterance.onpause = () => {
        if (!this.isCurrent(session)) return;
        this.motion.pause();
        this.onState("READY");
      };
      utterance.onresume = () => {
        if (!this.isCurrent(session)) return;
        this.motion.resume();
        this.onState("SPEAKING");
      };
      utterance.onend = utterance.onerror = () => this.finish(session);
      session.timer = this.env.setTimeout(() => this.finish(session), 10000);
      synth.speak(utterance);
    } catch { this.finish(session); }
  }

  destroy() {
    this.stop();
    this.context?.close().catch(() => {});
    this.context = null;
  }
}
