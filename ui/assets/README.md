# Cockpit assets

Artwork and font files in this directory are bundled with KIRA. The active MED
UI still imports Three.js from jsDelivr and a stylesheet from Google Fonts;
local artwork never needs an external image service at runtime.

## Active natural avatar

- `avatar-natural.webp` — original AI-generated **fictional photorealistic
  portrait**, 1024 × 1024, optimized to WebP (about 263 KiB). It is not a real
  person's likeness, a supplied reference photo or a live camera feed. Warm skin,
  natural eyes and pink lips are intentionally independent of the green HUD.
  The orbital halo, code and projector retain the green command-center theme.
- Only the outer image border has feathered alpha (56 px horizontally, 28 px at
  the top, 64 px at the bottom). Skin, hair, eyes and mouth remain opaque: dark
  features must not be keyed out and reveal green lights through the face.
- `avatar.mjs` preserves the portrait's RGB and alpha; `app.js` composites it
  **after** the background bloom. Both the face and animated mouth use the same
  material factory and brightness uniform. Do not add a global green tint,
  luminance-to-alpha key or bloom pass over the portrait.
- `holo-mouth.mjs` is calibrated for this specific image: lip seam at (512, 610),
  corners approximately (436, 610)–(588, 610), patch at (376, 552), 272 × 192 px.
  Replacing the image requires recalibrating this mesh as well. The patch is a
  coplanar child of the portrait plane so it follows the exact same projection.
  Skin/lips come from the portrait; cavity, tongue and teeth are procedural.
- Speech timing and motion preferences remain implemented in `lips.mjs` and
  `speech.mjs`; reduced motion and Motion Off return the mouth to its neutral
  photograph. The portrait itself has no scanline or glitch animation.

## Retained artwork and fonts

- `avatar_core.png`, `avatar_gold.png`, `avatar_final.png`, `avatar_matrix.png`,
  `avatar_notext.png`, `avatar_red.png` — earlier avatar artwork, retained but not
  used by the active natural-face renderer.
- `kira-hologram.webp` — earlier AI-generated android portrait (896 × 1200),
  used by the legacy `mouth.mjs` implementation, not the active MED avatar.
- `kira-mouth-interior.webp` — earlier AI-generated oral detail, cropped to a
  180 × 62 texture for that legacy portrait.
- `reticle.svg`, `projector.svg`, `neural-map.svg`, `binary-field.svg`,
  `kira-mark.svg` — original interface artwork. The neural map and binary field
  are decorative, not telemetry. Measured readings are rendered separately.
- `fonts/` — Latin WOFF2 subsets of Rajdhani, Orbitron and Share Tech Mono,
  plus Noto Sans Arabic (Arabic subset for RTL interface and messages),
  distributed by Fontsource. Each family's SIL Open Font License is included
  alongside its font files. System fallbacks remain available for other scripts.
