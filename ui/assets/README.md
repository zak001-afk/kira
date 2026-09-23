# Cockpit assets

These assets are bundled with KIRA. The interface makes no external artwork,
font, or rendering-library requests.

- `kira-hologram.webp` — original AI-generated android portrait, created for this
  redesign and optimized to WebP. A visual illustration, not a real person's
  likeness, live camera feed, or lip-synced model.
- `reticle.svg`, `projector.svg`, `neural-map.svg`, `binary-field.svg`,
  `kira-mark.svg` — original interface artwork. The neural map and binary field
  are decorative, not telemetry. Measured readings are rendered separately.
- `fonts/` — Latin WOFF2 subsets of Rajdhani, Orbitron and Share Tech Mono,
  distributed by Fontsource. Each family's SIL Open Font License is included
  alongside its font files. System fallbacks remain available for other scripts.

Animations and speech-driven transforms are implemented in `style.css` and
`hologram.mjs`, rather than baked into the images. All movement respects the
Auto / On / Off preference and system reduced motion in Auto mode.
