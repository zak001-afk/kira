// Portrait photographique fictif : les couleurs de peau ne suivent pas le thème HUD.
export const AVATAR_PORTRAIT = Object.freeze({
  url: "assets/avatar-natural.webp?v=natural-face-1",
  width: 1024,
  height: 1024,
});
export const AVATAR_BRIGHTNESS_DEFAULT = 0.9;

// Même rendu pour le portrait et le patch labial : couleurs sRGB de l'image,
// alpha réel, luminosité neutre. Aucun monochrome, scanline, glitch ou relighting.
// Le portrait est composé APRÈS le bloom du décor (voir app.js).
export function createPortraitMaterial(three, texture, brightness = AVATAR_BRIGHTNESS_DEFAULT) {
  // Lecture brute des valeurs sRGB, restituées sans double conversion gamma.
  texture.colorSpace = three.NoColorSpace;
  return new three.ShaderMaterial({
    uniforms: { map: { value: texture }, brightness: { value: brightness } },
    transparent: true,
    depthWrite: false,
    depthTest: false,
    toneMapped: false,
    blending: three.NormalBlending,
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform sampler2D map;
      uniform float brightness;
      varying vec2 vUv;
      void main() {
        vec4 portrait = texture2D(map, vUv);
        gl_FragColor = vec4(portrait.rgb * brightness, portrait.a);
      }`,
  });
}
