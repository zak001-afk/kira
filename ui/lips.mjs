// Fade d'attaque et de relâchement du gain de lecture : un flux TTS neural
// n'est jamais muet à son premier échantillon, un pause() immédiat coupe une
// forme d'onde encore sonore — deux sources certaines de clic audible.
export const AUDIO_ATTACK_SECONDS = 0.015;
export const AUDIO_RELEASE_SECONDS = 0.04;

// KIRA - Animation labiale naturelle et humaine
// Visèmes calibrés pour un avatar réaliste, pas une photo qui s'étire.
// Le mouvement suit la mâchoire (ouverture) + lèvres (arrondi/étirement) séparément.
const clamp = (n, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, Number.isFinite(n) ? n : 0));
const ease = n => { n = clamp(n); return n * n * (3 - 2 * n); };
const smoothStep = (a, b, t) => { t = clamp((t - a) / (b - a)); return t * t * (3 - 2 * t); };
const KEYS = ["open", "round", "wide", "bite", "press"];
export const REST_MOUTH = Object.freeze({ open: 0, round: 0, wide: 0, bite: 0, press: 0, viseme: "REST", source: "idle" });

// Pose factory: open = mâchoire, round = arrondissement, wide = sourire/étirement, bite = dents, press = fermeture
const pose = (open, round = 0, wide = 0, bite = 0, press = 0) => ({ open, round, wide, bite, press });

// Visèmes recalibrés pour naturel - ouverture réduite, mouvements plus subtils
// REST: bouche fermée détendue, lèvres jointes sans pression
// MBP: bilabiales - fermeture complète avec légère pression
// FV: labio-dentales - lèvre inférieure contre dents supérieures
// AH: voyelle ouverte - mâchoire basse, bouche ouverte naturelle (pas 90%)
// EE: voyelle fermée étirée - sourire léger, ouverture moyenne
// OH: voyelle mi-ouverte arrondie
// OO: voyelle fermée arrondie - petit trou
// etc.
export const VISEMES = Object.freeze({
  REST: pose(0, 0, 0, 0, 0.05),
  MBP: pose(0, 0, 0, 0, 1),
  FV: pose(0.14, 0, 0.18, 0.88, 0.08),
  AH: pose(0.85, 0, 0.06, 0, 0),           // Ouvert naturel - test exige >0.6 après 12 frames
  EE: pose(0.30, 0, 0.92, 0, 0),
  OH: pose(0.56, 0.68, 0, 0, 0),
  OO: pose(0.36, 0.90, 0, 0, 0),
  SS: pose(0.16, 0, 0.34, 0, 0.12),
  TH: pose(0.24, 0, 0.20, 0.32, 0),
  LL: pose(0.36, 0, 0.24, 0, 0),
  RR: pose(0.30, 0.24, 0.14, 0, 0),
  TD: pose(0.20, 0, 0.22, 0, 0.18),
  KG: pose(0.42, 0, 0.09, 0, 0),
  H: pose(0.34, 0, 0.06, 0, 0),
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
    const weight = ["AH", "OH", "OO"].includes(viseme) ? 1.5 : viseme === "EE" ? 1.3 : viseme === "MBP" ? 0.7 : 0.8;
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
    let left = 0, right = this.words.length - 1;
    while (left <= right) {
      const middle = (left + right) >> 1;
      if (this.words[middle].start <= elapsed) { word = this.words[middle]; left = middle + 1; }
      else right = middle - 1;
    }
    if (!word || elapsed > word.start + word.duration) {
      if (!this.measured && keepAlive && this.duration && elapsed > this.duration + 200) {
        const breath = 0.5 + 0.5 * Math.sin(elapsed / 420);
        return { ...VISEMES.AH, open: 0.18 + 0.12 * Math.sin(elapsed / 180) ** 2 * breath,
          round: 0.15 * breath, viseme: "REST", source };
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
    // Coarticulation naturelle: anticipation douce sans sauts
    if (phase < 0.28) return blend(previous, current, ease(phase / 0.28), cue.viseme, source);
    if (phase > 0.72) return blend(current, next, ease((phase - 0.72) / 0.28) * 0.55, cue.viseme, source);
    return { ...current, viseme: cue.viseme, source };
  }
}

export class LipMotion {
  constructor() { this.reset(); }
  reset() {
    this.pose = { ...REST_MOUTH };
    this.velocity = { open: 0, round: 0, wide: 0, bite: 0, press: 0 };
    this.last = null;
    this.jawMomentum = 0;
    return this.pose;
  }

  sample(voice, { now = 0, disabled = false, enabled = true, demo = null } = {}) {
    if (disabled || !enabled) return this.reset();
    const dt = this.last === null ? 1 / 30 : clamp((now - this.last) / 1000, 0, 0.12);
    this.last = now;
    const shape = demo || voice.mouth || REST_MOUTH;
    const active = Boolean(demo || voice.active);
    const rawSignal = demo ? 0.75 : clamp(voice.level ?? voice.energy ?? 0);

    // Porte douce: évite les déclenchements sur bruit faible
    // Seuil plus haut et courbe plus douce pour éviter le clignotement
    const gate = active ? smoothStep(0.015, 0.12, rawSignal) : 0;

    // Puissance avec compression: fort au début, puis plateau
    const power = demo ? 1 : 0.25 + 0.75 * Math.pow(clamp(rawSignal), 0.6);

    // Cible avec atténuation naturelle selon le type de visème
    let targetOpen = shape.open * gate * power;
    let targetRound = shape.round * gate * power;
    let targetWide = shape.wide * gate * power;
    let targetBite = shape.bite * gate * power;
    let targetPress = shape.press * gate;

    // Anti-pop: la fermeture MBP doit être instantanée, l'ouverture progressive
    if (shape.viseme === "MBP" && gate > 0.1) {
      targetPress = Math.max(targetPress, 0.85 * gate);
      targetOpen *= 0.15; // Presque fermé pour M/B/P
    }

    // FV: dents visibles mais pas grande ouverture
    if (shape.viseme === "FV") {
      targetOpen = Math.min(targetOpen, 0.18 * gate);
    }

    const targets = {
      open: clamp(targetOpen),
      round: clamp(targetRound),
      wide: clamp(targetWide),
      bite: clamp(targetBite),
      press: clamp(targetPress),
    };

    // Dynamique naturelle et stable: lissage exponentiel sans overshoot
    // Mâchoire plus lourde que lèvres, mais pas d'oscillation
    for (const key of KEYS) {
      const current = this.pose[key];
      const target = targets[key];
      const isOpening = target > current;

      let attack, release;
      if (key === "open") {
        attack = gate < 0.02 ? 0.018 : 0.024;
        release = gate < 0.02 ? 0.024 : 0.036;
      } else if (key === "press" || key === "bite") {
        attack = 0.016;
        release = 0.026;
      } else {
        attack = 0.018;
        release = gate < 0.02 ? 0.022 : 0.030;
      }

      const tau = isOpening ? attack : release;
      const alpha = 1 - Math.exp(-dt / tau);
      this.pose[key] += (target - this.pose[key]) * alpha;

      if (Math.abs(this.pose[key]) < 0.0005) this.pose[key] = 0;
      if (this.pose[key] > 0.998) this.pose[key] = 1;
      this.pose[key] = clamp(this.pose[key]);
    }
    // Reset momentum for compat
    this.jawMomentum *= 0.85;
    for (const k of KEYS) this.velocity[k] *= 0.85;

    // Corrélation naturelle: quand on ouvre beaucoup, l'arrondi diminue légèrement
    if (this.pose.open > 0.5 && this.pose.round > 0.3) {
      this.pose.round *= (1 - (this.pose.open - 0.5) * 0.25);
    }

    // Quand press est actif, open doit être minimal
    if (this.pose.press > 0.6) {
      this.pose.open *= (1 - this.pose.press * 0.85);
      this.pose.bite *= (1 - this.pose.press * 0.5);
    }

    this.pose.viseme = gate > 0.02 ? shape.viseme : "REST";
    this.pose.source = active ? (demo ? "demo" : shape.source) : "idle";
    return this.pose;
  }
}

export function lipDemoPose(age) {
  if (!Number.isFinite(age) || age < 0 || age >= 4.2) return null;
  const sequence = ["REST", "AH", "EE", "OO", "FV", "MBP", "REST"];
  const step = age / 0.6;
  const index = Math.min(sequence.length - 1, Math.floor(step));
  const previous = VISEMES[sequence[Math.max(0, index - 1)]];
  return blend(previous, VISEMES[sequence[index]], ease(Math.min(1, (step - index) / 0.35)), sequence[index], "demo");
}
