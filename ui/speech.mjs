import { speechLocale, matchingVoice } from "./locale.mjs";
import { AUDIO_ATTACK_SECONDS, AUDIO_RELEASE_SECONDS, VisemeTimeline, wordTimeline, REST_MOUTH } from "./lips.mjs";

// Audio-driven field and mouth timing. Only playback, never the microphone.
const clamp = (value, low = 0, high = 1) => Math.min(high, Math.max(low, value));

export function cleanForSpeech(text) {
  return String(text || "")
    .replace(/```[\s\S]*?```/g, "code block")
    .replace(/`[^`]+`/g, "")
    .replace(/https?:\/\/\S+/g, "link")
    .replace(/[0-9#*]\uFE0F?\u20E3|[\u{1F000}-\u{1FAFF}\u2600-\u27BF\u2300-\u23FF\u2B00-\u2BFF\u2194-\u2199\u21A9-\u21AA\u00A9\u00AE\u203C\u2049\u2122\u2139\u3030\u303D\u3297\u3299\uFE0E\uFE0F\u200D\u20E3\u{E0020}-\u{E007F}]/gu, "")
    .replace(/[*_~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

// Older embedded WebView2 runtimes may not implement Array.findLast.
function lastBefore(items, value, key) {
  for (let i = items.length - 1; i >= 0; i--) {
    if (items[i][key] <= value) return items[i];
  }
  return null;
}

export class SpeechMotion {
  constructor(now = () => performance.now()) {
    this.now = now;
    this.frame = { energy: 0, low: 0, high: 0, level: 0, active: false, source: "idle", mouth: { ...REST_MOUTH }, charIndex: 0 };
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
    this.hasBoundary = false;
    this.articulation = null;
    this.captionWords = [];
    this.captionLength = 0;
    this.audioOnset = null;
    this.onProgress = null;
    this.frame.mouth = { ...REST_MOUTH };
    this.frame.level = 0;
    this.frame.charIndex = 0;
    // Keep the envelope: sample() releases it gently back to idle.
  }

  startAudio(analyser, media, text, timings = []) {
    this.stop();
    this.mode = "audio";
    this.media = media;
    this.analyser = analyser;
    if (analyser) {
      this.floatSamples = typeof analyser.getFloatTimeDomainData === "function";
      this.wave = this.floatSamples ? new Float32Array(analyser.fftSize) : new Uint8Array(analyser.fftSize);
      this.bins = new Uint8Array(analyser.frequencyBinCount);
    }
    this.words = wordTimeline(text);
    this.articulation = new VisemeTimeline(text, { timings });
    this.captionLength = String(text || "").length;
    // Reuse the measured TTS word boundaries so the visible reply advances on
    // the same audio clock as the mouth; estimate only when metadata is absent.
    this.captionWords = wordTimeline(text).map((word, index) => {
      const measured = this.articulation.measured && this.articulation.words[index];
      return measured ? { ...word, start: measured.start, duration: measured.duration } : word;
    });
  }

  startBrowser(text, rate = 1) {
    this.stop();
    this.mode = "browser";
    this.started = this.now();
    this.words = wordTimeline(text, rate);
    this.captionWords = this.words;
    this.captionLength = String(text || "").length;
    this.articulation = new VisemeTimeline(text, { rate });
  }

  boundary(charIndex) {
    if (this.mode !== "browser" || !Number.isFinite(charIndex)) return;
    const word = lastBefore(this.words, charIndex, "index");
    this.hasBoundary = true;
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

  estimatedEnergy(elapsed, keepAlive = false) {
    const final = this.words[this.words.length - 1];
    const end = final ? final.start + final.duration : 0;
    // A voice can speak more slowly than our estimate. Keep gentle estimated
    // syllables until its real end event, rather than freezing mid-sentence.
    if (keepAlive && end && elapsed > end + 200) {
      return 0.18 + 0.3 * Math.sin((elapsed - end) / 125) ** 2;
    }
    const word = lastBefore(this.words, elapsed, "start");
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
      if (this.floatSamples) this.analyser.getFloatTimeDomainData(this.wave);
      else this.analyser.getByteTimeDomainData(this.wave);
      let squares = 0;
      for (const value of this.wave) squares += (this.floatSamples ? value : (value - 128) / 128) ** 2;
      // Float samples preserve quiet voices that disappear in 8-bit samples.
      // Soft gain makes low-volume speech visible without animating silence.
      energy = Math.pow(clamp((Math.sqrt(squares / this.wave.length) - 0.001) * 5), 0.65);
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
      let elapsed = this.mode === "audio"
        ? this.media.currentTime * 1000
        : now - this.started + this.offset;
      if (this.mode === "audio" && Number.isFinite(this.media.duration) && this.media.duration > 0) {
        const final = this.words[this.words.length - 1];
        if (final) elapsed *= (final.start + final.duration) / (this.media.duration * 1000);
      }
      energy = this.estimatedEnergy(elapsed, true);
      low = energy * 0.45;
      high = energy * 0.3;
    }
    this.frame.level = energy; // Unsmeared signal closes the lips during silence.
    this.frame.mouth = { ...REST_MOUTH };
    if (active && this.articulation) {
      let elapsed = now - this.started + this.offset;
      let duration = 0;
      let ready = true;
      if (this.mode === "audio") {
        elapsed = this.media.currentTime * 1000;
        duration = Number.isFinite(this.media.duration) ? this.media.duration * 1000 : 0;
        // With no word metadata, remove leading decoder/TTS silence from the
        // estimated timeline. The actual media clock still controls progression.
        if (this.analyser && !this.articulation.measured) {
          if (this.audioOnset === null && energy > 0.012) this.audioOnset = elapsed;
          ready = this.audioOnset !== null;
          elapsed = Math.max(0, elapsed - (this.audioOnset || 0));
          duration = Math.max(0, duration - (this.audioOnset || 0));
        }
      }
      if (ready) {
        this.frame.mouth = this.articulation.sample(elapsed, {
          duration, boundaries: this.hasBoundary, keepAlive: this.mode === "browser",
        });
        let captionElapsed = elapsed;
        if (this.mode === "audio" && !this.articulation.measured && duration > 0) {
          captionElapsed *= this.articulation.duration / duration;
        }
        const captionWord = lastBefore(this.captionWords, captionElapsed, "start");
        if (captionWord) this.frame.charIndex = captionWord.index + captionWord.text.length;
        if (this.onProgress) this.onProgress(this.frame.charIndex);
      }
    }
    for (const [key, target] of [["energy", energy], ["low", low], ["high", high]]) {
      const attack = key === "energy" ? 0.058 : 0.065;
      const release = key === "energy" ? 0.11 : 0.14;
      const tau = target > this.frame[key] ? attack : release;
      const smoothing = 1 - Math.exp(-dt / tau);
      this.frame[key] += (target - this.frame[key]) * smoothing;
      if (this.frame[key] < 0.0003) this.frame[key] = 0;
    }
    this.frame.active = active;
    this.frame.source = !active ? "idle" : this.analyser ? "audio"
      : this.hasBoundary ? "words" : "estimated";
    return this.frame;
  }
}

export class SpeechPlayer {
  constructor({ fetchAudio, onState = () => {}, onNotice = () => {}, env = globalThis, motion } = {}) {
    this.env = env;
    this.fetchAudio = fetchAudio;
    this.onState = onState;
    this.onNotice = onNotice;
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
    session.gain?.disconnect();
    session.analyser?.disconnect();
    if (session.url) this.env.URL.revokeObjectURL(session.url);
    session.audio = session.url = session.source = session.gain = session.analyser = null;
  }

  // Clic audible à l'attaque : un flux TTS neural commence rarement par du
  // silence, donc une lecture qui démarre à pleine amplitude claque. La
  // lecture passe par un GainNode avec micro-fondu d'entrée ; le toucher au
  // volume reste bref (<20 ms) et n'influence ni la vitesse ni la bouche.
  _connectAudio(session, audio) {
    if (this.context?.state !== "running") return;
    try {
      session.analyser = this.context.createAnalyser();
      session.analyser.fftSize = 1024;
      session.analyser.smoothingTimeConstant = 0.55;
      session.source = this.context.createMediaElementSource(audio);
      session.gain = this.context.createGain();
      session.gain.gain.setValueAtTime(0, this.context.currentTime);
      session.gain.gain.linearRampToValueAtTime(1, this.context.currentTime + AUDIO_ATTACK_SECONDS);
      session.source.connect(session.analyser);
      session.analyser.connect(session.gain);
      session.gain.connect(this.context.destination);
    } catch {
      // Si le routage a partiellement réussi, on restaure un chemin direct audible.
      session.source?.disconnect();
      session.gain?.disconnect();
      session.analyser?.disconnect();
      session.source?.connect(this.context.destination);
      session.gain = session.analyser = null;
    }
  }

  // Relâche le gain en douceur avant le pause() : couper un flux encore
  // sonore produit le même claquement qu'un mauvais splice audio. On ne
  // ré-ancre PAS la valeur : le ramp s'enchaîne sur la courbe en cours, donc
  // aucune discontinuité même au cœur du fondu d'entrée.
  _scheduleEndFade(session, audio) {
    if (!session.gain || session.endFade) return;
    if (!Number.isFinite(audio?.duration) || audio.duration <= 0) return;
    try {
      const now = this.context.currentTime;
      // Le fondu final démarre après l'attaque, jamais au milieu d'elle.
      const start = Math.max(now + AUDIO_ATTACK_SECONDS, now + audio.duration - audio.currentTime - AUDIO_RELEASE_SECONDS);
      session.gain.gain.setValueAtTime(1, start);
      session.gain.gain.linearRampToValueAtTime(0, start + AUDIO_RELEASE_SECONDS);
      session.endFade = true;
    } catch { /* non critique : la fin du clip reste dans son état d'origine. */ }
  }

  finish(session) {
    if (this.session !== session) return;
    this.session = null; // invalidate callbacks before cancelling playback
    if (session.onProgress) session.onProgress(session.text.length);
    this.clearTimer(session);
    session.abort.abort();
    this.releaseMedia(session);
    if (session.voicesChanged) this.env.speechSynthesis?.removeEventListener?.("voiceschanged", session.voicesChanged);
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

  async speak(text, { language = "en-US", onProgress = null } = {}) {
    this.stop();
    const cleanText = cleanForSpeech(text);
    if (!this.enabled || !cleanText) return;
    const session = {
      abort: new this.env.AbortController(), fallback: false,
      language: speechLocale(language), text: cleanText,
      onProgress: typeof onProgress === "function" ? onProgress : null,
    };
    this.session = session;
    this.unlock();
    this.onState("THINKING");
    // Also handles a fetch implementation that never resolves after abort.
    session.timer = this.env.setTimeout(() => this.fallback(session, cleanText), 15000);
    try {
      const data = await this.fetchAudio(cleanText, { signal: session.abort.signal, language: session.language });
      if (!this.isCurrent(session) || session.fallback) return;
      this.clearTimer(session);
      if (data.error || !data.audio) throw new Error(data.error || "No speech audio");
      const bytes = Uint8Array.from(this.env.atob(data.audio), (char) => char.charCodeAt(0));
      const mime = data.format === "wav" ? "audio/wav" : "audio/mpeg";
      session.url = this.env.URL.createObjectURL(new this.env.Blob([bytes], { type: mime }));
      const audio = session.audio = new this.env.Audio(session.url);
      // Do not route audio into a suspended context: that would mute it.
      this._connectAudio(session, audio);
      audio.onplaying = () => {
        if (!this.isCurrent(session) || session.fallback) return;
        this._scheduleEndFade(session, audio);
        if (this.motion.mode === "audio" && this.motion.media === audio) this.motion.resume();
        else this.motion.startAudio(session.analyser, audio, cleanText, data.word_timings);
        this.motion.onProgress = session.onProgress;
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
      this.onNotice("voice-unavailable", { language: session.language });
      this.finish(session);
      return;
    }
    const start = voice => {
      if (!this.isCurrent(session)) return;
      this.clearTimer(session);
      if (session.voicesChanged) synth.removeEventListener?.("voiceschanged", session.voicesChanged);
      session.voicesChanged = null;
      try {
        const utterance = session.utterance = new this.env.SpeechSynthesisUtterance(text);
        utterance.lang = session.language;
        utterance.voice = voice;
        utterance.rate = 0.95;
        utterance.pitch = 1.1;
        utterance.volume = 1;
        utterance.onstart = () => {
          if (!this.isCurrent(session)) return;
          this.clearTimer(session);
          this.motion.startBrowser(text, utterance.rate);
          this.motion.onProgress = session.onProgress;
          this.onState("SPEAKING");
        };
        utterance.onboundary = event => {
          if (this.isCurrent(session) && (!event.name || event.name === "word")) this.motion.boundary(event.charIndex);
        };
        utterance.onpause = () => {
          if (!this.isCurrent(session)) return;
          this.motion.pause(); this.onState("READY");
        };
        utterance.onresume = () => {
          if (!this.isCurrent(session)) return;
          this.motion.resume(); this.onState("SPEAKING");
        };
        utterance.onend = () => this.finish(session);
        utterance.onerror = () => {
          if (this.isCurrent(session)) this.onNotice("voice-unavailable", { language: session.language });
          this.finish(session);
        };
        session.timer = this.env.setTimeout(() => this.finish(session), 10000);
        synth.speak(utterance);
      } catch {
        this.onNotice("voice-unavailable", { language: session.language });
        this.finish(session);
      }
    };
    const unavailable = () => {
      if (!this.isCurrent(session)) return;
      this.onNotice("voice-unavailable", { language: session.language });
      this.finish(session);
    };
    try {
      const voice = matchingVoice(synth.getVoices(), session.language);
      if (voice) { start(voice); return; }
      // Browser voice catalogs can load late. Wait once, with cancellation and a
      // deadline; never silently read French through an English default voice.
      if (!synth.addEventListener) { unavailable(); return; }
      session.voicesChanged = () => {
        if (!this.isCurrent(session)) return;
        const found = matchingVoice(synth.getVoices(), session.language);
        if (found) start(found);
      };
      synth.addEventListener("voiceschanged", session.voicesChanged);
      session.timer = this.env.setTimeout(unavailable, 1200);
    } catch { unavailable(); }
  }

  destroy() {
    this.stop();
    this.context?.close().catch(() => {});
    this.context = null;
  }
}
