# Cockpit assets

These assets are bundled with KIRA. The interface makes no external artwork,
font, or rendering-library requests.

- `kira-hologram.webp` — original AI-generated android portrait, created for this
  redesign and optimized to WebP. A visual illustration, not a real person's
  likeness or live camera feed. A hand-defined 2D mouth mesh now deforms this
  specific portrait during spoken replies.
- `kira-mouth-interior.webp` — AI-generated oral detail based on the same portrait,
  cropped to a 180 × 62 texture for teeth/cavity inside the animated lip contour.
  The lips and surrounding skin still come from the original portrait.
- `reticle.svg`, `projector.svg`, `neural-map.svg`, `binary-field.svg`,
  `kira-mark.svg` — original interface artwork. The neural map and binary field
  are decorative, not telemetry. Measured readings are rendered separately.
- `fonts/` — Latin WOFF2 subsets of Rajdhani, Orbitron and Share Tech Mono,
  plus Noto Sans Arabic (Arabic subset for RTL interface and messages),
  distributed by Fontsource. Each family's SIL Open Font License is included
  alongside its font files. System fallbacks remain available for other scripts.

Animations and speech-driven transforms are implemented in `style.css` and
`hologram.mjs`, `lips.mjs` and `mouth.mjs`, rather than baked into the images. All movement respects the
Auto / On / Off preference and system reduced motion in Auto mode.
