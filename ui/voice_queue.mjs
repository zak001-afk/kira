import { cleanForSpeech } from "./speech.mjs";

// Sentence-by-sentence speech queue.
//
// KIRA's replies are split by the backend speech formatter (POST /api/tts/plan)
// into short spoken sentences. This queue fetches and plays them one at a time
// so the voice starts on the first sentence instead of waiting for the whole
// reply to be synthesized. Clips never overlap: each one waits for the previous
// playback to end. stop() is the barge-in: it aborts the in-flight clip and
// drops everything still queued.

const SENTENCE_END = /([.!?…]+["')\]]*)\s+/;
const MAX_SENTENCES = 4;

// Human pacing: how long to wait between two sentences. The speaking mode owns
// this (normal 0.45 s, serious 0.60 s, alert 0.14 s …) and a clip already ends
// with ~110 ms of natural decay, so the mode's pause is what is left to wait.
const CLIP_TAIL_MS = 110;
const DEFAULT_GAP_MS = 340;   // normal mode, when the plan carries no profile
const MIN_GAP_MS = 120;
const MAX_GAP_MS = 700;
// A reply that waits an exact number of milliseconds every time reads as a
// machine: sentences breathe slightly differently from one to the next.
const PACE_WOBBLE = [1, 0.94, 1.06];

export function paceGapMs(profile, explicit) {
  if (Number.isFinite(explicit)) return explicit;  // caller override (tests, tuning)
  const pause = Number(profile?.sentence_pause);
  if (!Number.isFinite(pause)) return DEFAULT_GAP_MS;
  return Math.round(Math.min(MAX_GAP_MS, Math.max(MIN_GAP_MS, pause * 1000 - CLIP_TAIL_MS)));
}

export function localSentences(text, limit = MAX_SENTENCES) {
  const clean = cleanForSpeech(text);
  if (!clean) return [];
  const parts = clean.split(SENTENCE_END).reduce((list, piece, index) => {
    if (index % 2 === 0) {
      const head = piece.trim();
      if (head) list.push(head);
    } else if (list.length) {
      list[list.length - 1] += piece;
    }
    return list;
  }, []);
  const sentences = parts.map(part => part.trim()).filter(Boolean);
  if (limit > 0 && sentences.length > limit) return sentences.slice(0, limit);
  return sentences.length ? sentences : [clean];
}

export class VoiceQueue {
  constructor({ player, apiBase = "", fetchImpl, env = globalThis, gapMs = null, onState = () => {}, onNotice = () => {} } = {}) {
    this.player = player;
    this.apiBase = apiBase;
    this.fetchImpl = fetchImpl || ((url, init) => env.fetch(url, init));
    this.env = env;
    this.gapMs = gapMs;
    this.onState = onState;
    this.onNotice = onNotice;
    this.session = null;
    this.serial = 0;
    // Take over the player's state channel so the multi-clip loop can smooth
    // the READY/THINKING flicker that would otherwise appear between clips.
    this._playerState = player.onState;
    player.onState = state => this._handlePlayerState(state);
  }

  get speaking() {
    return Boolean(this.session && !this.session.aborted);
  }

  _emit(state) {
    if (this._playerState) this._playerState(state);
    this.onState(state);
  }

  _handlePlayerState(state) {
    const session = this.session;
    if (session && !session.aborted && state === "READY") {
      const last = session.index >= session.sentences.length - 1;
      session.clipDone?.();
      if (!last) {
        // More sentences to play: keep SPEAKING between clips.
        this._emit("SPEAKING");
        return;
      }
    }
    this._emit(state);
  }

  async _plan(text, mode) {
    try {
      const response = await this.fetchImpl(`${this.apiBase}/api/tts/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, mode }),
      });
      if (!response.ok) return null;
      const data = await response.json();
      const sentences = Array.isArray(data?.sentences) ? data.sentences.filter(Boolean) : [];
      return sentences.length ? { sentences, profile: data?.profile } : null;
    } catch {
      return null; // the plan is an optimization: fall back to local splitting
    }
  }

  _wait(ms) {
    if (!(ms > 0)) return Promise.resolve();
    return new Promise(resolve => this.env.setTimeout(resolve, ms));
  }

  async speak(text, options = {}) {
    this.stop();
    if (!this.player.enabled) return;
    const session = {
      id: ++this.serial, aborted: false, index: 0, sentences: [], offsets: [],
      options, onProgress: typeof options.onProgress === "function" ? options.onProgress : null,
      clipDone: null, resolveFirst: null, firstClip: null,
    };
    session.firstClip = new Promise(resolve => { session.resolveFirst = resolve; });
    this.session = session;
    const plan = await this._plan(text, options.mode || "normal");
    if (session.aborted || this.session !== session) return;
    const sentences = plan?.sentences || localSentences(text);
    if (!sentences.length) return;
    session.gap = paceGapMs(plan?.profile, this.gapMs);
    session.sentences = sentences;
    const spokenTotal = sentences.join("\n\n").length || 1;
    let offset = 0;
    session.offsets = sentences.map(sentence => {
      const current = offset;
      offset += sentence.length + 2;
      return current;
    });
    session.spokenTotal = spokenTotal;
    session.textLength = String(text || "").length || spokenTotal;
    this._run(session);
    return session.firstClip;
  }

  async _run(session) {
    try {
      for (let index = 0; index < session.sentences.length; index++) {
        if (session.aborted || this.session !== session) return;
        session.index = index;
        const sentence = session.sentences[index];
        const multi = session.sentences.length > 1;
        const progress = session.onProgress
          ? charIndex => {
              // Map clip-local progress onto the original reply's text length
              // so the UI reveal keeps a stable, proportional timeline.
              const within = Math.min(charIndex, sentence.length);
              const fraction = (session.offsets[index] + within) / session.spokenTotal;
              session.onProgress(Math.round(Math.min(1, fraction) * session.textLength));
            }
          : null;
        const clip = this.player.speak(sentence, {
          language: session.options.language,
          mode: session.options.mode,
          onProgress: multi ? progress : session.onProgress,
        });
        if (index === 0) {
          Promise.resolve(clip).then(
            () => session.resolveFirst?.(),
            () => session.resolveFirst?.(),
          );
        }
        if (index > 0 || session.sentences.length > 1) {
          await new Promise(resolve => { session.clipDone = resolve; });
        } else {
          await clip;
        }
        if (session.aborted || this.session !== session) return;
        if (index < session.sentences.length - 1) {
          await this._wait(Math.round(session.gap * PACE_WOBBLE[index % PACE_WOBBLE.length]));
        }
      }
    } catch {
      this.onNotice("voice-playback-failed");
    } finally {
      if (this.session === session) {
        this.session = null;
        session.resolveFirst?.();
      }
    }
  }

  stop() {
    const session = this.session;
    this.session = null;
    if (session) {
      session.aborted = true;
      session.clipDone?.();
      this.player.stop();
      this._emit("INTERRUPTED");
      this._wait(900).then(() => {
        if (!this.session) this._emit("READY");
      });
    } else {
      this.player.stop();
    }
  }

  destroy() {
    this.stop();
    this.player.onState = this._playerState;
  }
}
