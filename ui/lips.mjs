// Lightweight 2D articulation. Word times can be measured; visemes are spelling
// heuristics, NOT a phoneme recognizer or a language-independent forced aligner.
const clamp = (n, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, Number.isFinite(n) ? n : 0));
const ease = n => { n = clamp(n); return n * n * (3 - 2 * n); };
const KEYS = ["open", "round", "wide", "bite", "press"];
export const REST_MOUTH = Object.freeze({ open: 0, round: 0, wide: 0, bite: 0, press: 0, viseme: "REST", source: "idle" });
const pose = (open, round = 0, wide = 0, bite = 0, press = 0) => ({ open, round, wide, bite, press });
export const VISEMES = Object.freeze({
  REST: pose(0), MBP: pose(0, 0, 0, 0, 1), FV: pose(0.17, 0, 0.25, 1),
  AH: pose(0.9, 0, 0.08), EE: pose(0.4, 0, 1), OH: pose(0.78, 0.8),
  OO: pose(0.53, 1), SS: pose(0.2, 0, 0.4), TH: pose(0.34, 0, 0.25),
  LL: pose(0.47, 0, 0.3), RR: pose(0.4, 0.3), TD: pose(0.27, 0, 0.3),
  KG: pose(0.55), H: pose(0.5),
});

export function wordTimeline(text, rate = 1) {
  rate = clamp(rate, 0.25, 3) || 1;
  let start = 0;
  return Array.from(String(text || "").matchAll(/\S+/gu), match => {
    const duration = (110 + Math.min(match[0].length, 12) * 30) / rate;
    const word = { index: match.index, text: match[0], start, duration };
    start += duration + (/[.!?…؟]$/.test(match[0]) ? 260 : /[,;:،؛]$/.test(match[0]) ? 120 : 35);
    return word;
  });
}

function cueFor(token) {
  if (/^[mbpمبپ]$/.test(token)) return "MBP";
  if (/^(ph|[fvفڤ])$/.test(token)) return "FV";
  if (/^(th|[ثذظ])$/.test(token)) return "TH";
  if (/^(eau|oo|ou|[uwوؤ])$/.test(token)) return "OO";
  if (/^(oa|au|ow|oi|oy|o)$/.test(token)) return "OH";
  if (/^(ee|ea|ai|ay|ei|ie|[eiyيئى])$/.test(token)) return "EE";
  if (/^[aاأإآعح]$/.test(token)) return "AH";
  if (/^(ch|sh|sch|tch|ss|[cszjسشصزجژ])$/.test(token)) return "SS";
  if (/^(ll|[lل])$/.test(token)) return "LL";
  if (/^(rr|[rرغ])$/.test(token)) return "RR";
  if (/^[dtnطدضتةن]$/.test(token)) return "TD";
  if (/^[kgqxقكخغ]$/.test(token)) return "KG";
  if (/^[hه]$/.test(token)) return "H";
  return "AH";
}

export function wordCues(text) {
  const normalized = String(text || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f\u064b-\u065f\u0670]/g, "");
  const tokens = normalized.match(/eau|tch|sch|ch|sh|th|ph|oo|ou|ow|oa|au|oi|oy|ee|ea|ai|ay|ei|ie|ll|rr|ss|[a-z\u0621-\u064a\u0671-\u06d3]/gu) || ["a"];
  const cues = tokens.map(token => {
    const viseme = cueFor(token);
    const weight = ["AH", "EE", "OH", "OO"].includes(viseme) ? 1.6 : viseme === "MBP" ? 0.85 : 0.75;
    return { viseme, weight };
  });
  const total = cues.reduce((sum, cue) => sum + cue.weight, 0);
  let offset = 0;
  return cues.map(cue => {
    const start = offset;
    offset += cue.weight / total;
    return { viseme: cue.viseme, start, end: offset };
  });
}

// The API uses seconds; the animation clock uses milliseconds. Bad/old metadata
// is ignored, never allowed to produce NaN transforms or break audio playback.
function timedWords(timings) {
  if (!Array.isArray(timings)) return [];
  const result = [];
  let previous = -1;
  for (const word of timings.slice(0, 10000)) {
    if (!word || typeof word.text !== "string" || !word.text.trim()
      || !Number.isFinite(word.start) || !Number.isFinite(word.duration)
      || word.start < 0 || word.duration <= 0 || word.duration > 60 || word.start < previous) continue;
    result.push({ text: word.text, start: word.start * 1000, duration: word.duration * 1000 });
    previous = word.start;
  }
  return result;
}

function blend(a, b, weight, viseme, source) {
  const result = { viseme, source };
  for (const key of KEYS) result[key] = a[key] + (b[key] - a[key]) * weight;
  return result;
}

export class VisemeTimeline {
  constructor(text, { rate = 1, timings = [] } = {}) {
    const aligned = timedWords(timings);
    this.measured = aligned.length > 0;
    this.words = (this.measured ? aligned : wordTimeline(text, rate)).map(word => ({ ...word, cues: wordCues(word.text) }));
    const last = this.words[this.words.length - 1];
    this.duration = last ? last.start + last.duration : 0;
  }

  sample(milliseconds, { duration = 0, boundaries = false, keepAlive = false } = {}) {
    let elapsed = Math.max(0, Number.isFinite(milliseconds) ? milliseconds : 0);
    if (!this.measured && Number.isFinite(duration) && duration > 0) elapsed *= this.duration / duration;
    const source = this.measured ? "word-timings" : boundaries ? "word-events" : "estimated";
    let word = null;
    // Binary search avoids scanning a long response thirty times per second.
    let left = 0, right = this.words.length - 1;
    while (left <= right) {
      const middle = (left + right) >> 1;
      if (this.words[middle].start <= elapsed) { word = this.words[middle]; left = middle + 1; }
      else right = middle - 1;
    }
    if (!word || elapsed > word.start + word.duration) {
      // Only un-timed browser voices need a slower-than-estimated fallback.
      // Measured word intervals and the media clock NEVER loop after their end.
      if (!this.measured && keepAlive && this.duration && elapsed > this.duration + 200) {
        return { ...VISEMES.AH, open: 0.42 + 0.22 * Math.sin(elapsed / 130) ** 2,
          round: 0.35 * (0.5 + 0.5 * Math.sin(elapsed / 330)), viseme: "AH", source };
      }
      return { ...REST_MOUTH, source };
    }
    const progress = clamp((elapsed - word.start) / word.duration);
    const found = word.cues.findIndex(cue => progress <= cue.end);
    const index = found < 0 ? word.cues.length - 1 : found;
    const cue = word.cues[index];
    const phase = clamp((progress - cue.start) / (cue.end - cue.start));
    const current = VISEMES[cue.viseme];
    const previous = index ? VISEMES[word.cues[index - 1].viseme] : VISEMES.REST;
    const next = index + 1 < word.cues.length ? VISEMES[word.cues[index + 1].viseme] : VISEMES.REST;
    // Coarticulation: anticipate the next shape without hard per-letter jumps.
    if (phase < 0.24) return blend(previous, current, ease(phase / 0.24), cue.viseme, source);
    if (phase > 0.8) return blend(current, next, ease((phase - 0.8) / 0.2) * 0.7, cue.viseme, source);
    return { ...current, viseme: cue.viseme, source };
  }
}

export class LipMotion {
  constructor() { this.reset(); }
  reset() { this.pose = { ...REST_MOUTH }; this.last = null; return this.pose; }

  sample(voice, { now = 0, disabled = false, enabled = true, demo = null } = {}) {
    if (disabled || !enabled) return this.reset();
    const dt = this.last === null ? 1 / 30 : clamp((now - this.last) / 1000, 0, 0.1);
    this.last = now;
    const shape = demo || voice.mouth || REST_MOUTH;
    const active = Boolean(demo || voice.active);
    const signal = demo ? 0.8 : clamp(voice.level ?? voice.energy ?? 0);
    const gate = active ? ease((signal - 0.006) / 0.075) : 0;
    const power = 0.32 + 0.68 * Math.sqrt(signal);
    const target = {
      open: shape.open * gate * power,
      round: shape.round * gate,
      wide: shape.wide * gate,
      bite: shape.bite * gate,
      press: shape.press * gate,
    };
    for (const key of KEYS) {
      const value = clamp(target[key]);
      const attack = key === "open" ? 0.028 : 0.042;
      const release = !gate ? 0.045 : 0.055;
      this.pose[key] += (value - this.pose[key]) * (1 - Math.exp(-dt / (value > this.pose[key] ? attack : release)));
      if (this.pose[key] < 0.0005) this.pose[key] = 0;
    }
    this.pose.viseme = gate > 0.01 ? shape.viseme : "REST";
    this.pose.source = active ? (demo ? "demo" : shape.source) : "idle";
    return this.pose;
  }
}

// A clearly labelled, finite visual check; never drives ordinary idle speech.
export function lipDemoPose(age) {
  if (!Number.isFinite(age) || age < 0 || age >= 4.2) return null;
  const sequence = ["REST", "AH", "EE", "OO", "FV", "MBP", "REST"];
  const step = age / 0.6;
  const index = Math.min(sequence.length - 1, Math.floor(step));
  const previous = VISEMES[sequence[Math.max(0, index - 1)]];
  return blend(previous, VISEMES[sequence[index]], ease(Math.min(1, (step - index) / 0.35)), sequence[index], "demo");
}
