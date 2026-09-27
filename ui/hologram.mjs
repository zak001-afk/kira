import { MouthAnimator } from "./mouth.mjs";

// Offline speech-reactive field and 2D facial compositor. No microphone sampling.
const clamp = (n, max = 1) => Math.min(max, Math.max(0, Number(n) || 0));

export function projectionFrame(voice, { disabled = false, demoEnergy = null, time = 0 } = {}) {
  const level = clamp(demoEnergy === null ? voice.energy : demoEnergy);
  const energy = disabled ? 0 : level;
  const low = disabled ? 0 : clamp(demoEnergy === null ? voice.low : level * 0.6);
  const high = disabled ? 0 : clamp(demoEnergy === null ? voice.high : level * 0.3);
  return {
    energy, low, high,
    light: level * (disabled ? 0.12 : 1),
    haloX: 1 + energy * 0.065 + low * 0.025,
    haloY: 1 + energy * 0.095,
    portraitScale: 1 + energy * 0.018,
    portraitY: disabled ? 0 : Math.sin(time * 3.5) * energy * -3,
    time: disabled ? 0 : time,
  };
}

export function waveformPath(energy, time = 0) {
  const level = clamp(energy);
  const amplitude = 0.6 + level * 13;
  let path = "";
  for (let i = 0; i <= 100; i++) {
    const x = i * 2.5;
    const envelope = Math.sin(i / 100 * Math.PI) ** 1.5;
    const signal = Math.sin(i * 2.7 + time * 11) * Math.cos(i * 0.39 - time * 7);
    const y = 17 + signal * amplitude * envelope;
    path += `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(2)}`;
  }
  return path;
}

export class Hologram {
  constructor(document) {
    this.root = document.getElementById("hologram");
    this.halo = document.getElementById("halo");
    this.portrait = document.getElementById("portrait");
    this.wave = document.getElementById("voice-wave");
    this.mouth = new MouthAnimator(document);
    this.segments = [];
    const container = document.getElementById("activity-segments");
    for (let i = 0; i < 28; i++) {
      const segment = document.createElement("span");
      container.appendChild(segment);
      this.segments.push(segment);
    }
    this.frame = projectionFrame({ energy: 0, low: 0, high: 0 });
  }

  update(voice, options = {}) {
    const frame = this.frame = projectionFrame(voice, options);
    this.root.style.setProperty("--voice", frame.light.toFixed(4));
    this.halo.style.filter = `brightness(${(1 + frame.light * 0.25 + frame.high * 0.8).toFixed(3)})`;
    this.halo.style.transform = `scale(${frame.haloX.toFixed(4)}, ${frame.haloY.toFixed(4)})`;
    // The portrait is optional: the center can be a pure holographic core.
    if (this.portrait) this.portrait.style.transform = `translateY(${frame.portraitY.toFixed(3)}px) scale(${frame.portraitScale.toFixed(4)})`;
    // A static, very quiet trace when idle. Movement only comes from speech/test.
    this.wave.setAttribute("d", waveformPath(frame.energy, frame.energy > 0.002 ? frame.time : 0));
    this.segments.forEach((segment, i) => segment.classList.toggle("lit", i < Math.round(frame.energy * 28)));
    frame.mouth = this.mouth.update(voice, {
      now: (options.time || 0) * 1000, disabled: options.disabled,
      enabled: options.lipsEnabled !== false, demo: options.lipDemo,
    });
    return frame;
  }

  destroy() { this.mouth.destroy(); }
}
