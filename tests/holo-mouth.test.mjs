import test from "node:test";
import assert from "node:assert/strict";
import { HoloMouth, createMouthMesh, deformMouth, MOUTH_REGION } from "../ui/holo-mouth.mjs";
import { AVATAR_PORTRAIT } from "../ui/avatar.mjs";
import { REST_MOUTH, VISEMES } from "../ui/lips.mjs";

const signedArea = (vertices, triangle) => {
  const [a, b, c] = triangle.map(index => index * 2);
  return (vertices[b] - vertices[a]) * (vertices[c + 1] - vertices[a + 1])
    - (vertices[c] - vertices[a]) * (vertices[b + 1] - vertices[a + 1]);
};

test("the active lip mesh is calibrated to the natural portrait, not the old android", () => {
  assert.equal(AVATAR_PORTRAIT.width, 1024);
  assert.equal(AVATAR_PORTRAIT.height, 1024);
  const mesh = createMouthMesh();
  const xs = [], ys = [];
  for (let i = 0; i < 48; i++) {
    xs.push(mesh.vertices[i * 2] + MOUTH_REGION.x);
    ys.push(mesh.vertices[i * 2 + 1] + MOUTH_REGION.y);
  }
  assert.equal(Math.min(...xs), 436);
  assert.equal(Math.max(...xs), 588);
  assert.ok(Math.abs(ys.reduce((a, b) => a + b) / ys.length - 610) < 1);
  assert.deepEqual(deformMouth(REST_MOUTH), mesh.vertices);
});

test("every spoken viseme keeps the surrounding skin fixed and its triangles unfolded", () => {
  const mesh = createMouthMesh();
  for (const [name, pose] of Object.entries(VISEMES)) {
    const points = deformMouth(pose);
    // The outside ring cannot move: no sliding rectangular patch on the face.
    for (let i = 48 * 4 * 2; i < points.length; i++) {
      assert.equal(points[i], mesh.vertices[i], `${name}: skin boundary moved`);
    }
    for (const triangle of mesh.triangles) {
      assert.ok(signedArea(points, triangle) * signedArea(mesh.vertices, triangle) >= -0.0001,
        `${name}: lip triangle folded over`);
    }
  }
});

test("opening and rounding articulate the actual lips without shifting the face", () => {
  const mesh = createMouthMesh();
  const opened = deformMouth(VISEMES.AH), rounded = deformMouth(VISEMES.OO);
  const bottom = 12 * 2, top = 36 * 2;
  assert.ok(opened[bottom + 1] > mesh.vertices[bottom + 1] + 20);
  assert.ok(opened[top + 1] < mesh.vertices[top + 1]);
  assert.ok(rounded[0] < mesh.vertices[0] - 10);
  // Lip corners stay on the same level as the closed photograph.
  assert.equal(opened[1], mesh.vertices[1]);
  assert.equal(opened[24 * 2 + 1], mesh.vertices[24 * 2 + 1]);
});

test("invalid and extreme input stays finite and inside the portrait patch", () => {
  for (const pose of [
    ...Object.values(VISEMES), {},
    { open: NaN, wide: Infinity, round: -100, press: 1000, bite: -Infinity },
    { open: 100, wide: 100, round: 100, press: 100, bite: 100 },
  ]) {
    const output = new Float32Array(createMouthMesh().vertices.length);
    assert.equal(deformMouth(pose, output), output, "animation should reuse its buffer");
    for (let i = 0; i < output.length; i += 2) {
      assert.ok(Number.isFinite(output[i]) && Number.isFinite(output[i + 1]));
      assert.ok(output[i] >= 0 && output[i] <= MOUTH_REGION.width);
      assert.ok(output[i + 1] >= 0 && output[i + 1] <= MOUTH_REGION.height);
    }
  }
});

// An uncalibrated image must not draw a mouth over the wrong part of the face.
test("mismatched portrait dimensions leave the mouth safely disabled", () => {
  for (const image of [null, {}, { naturalWidth: 1024, naturalHeight: 1200 },
    { naturalWidth: 896, naturalHeight: 1024 }]) {
    const mouth = new HoloMouth(image, {}, {}, {});
    assert.equal(mouth.ready, false);
    assert.equal(mouth.update({}, { now: 100 }), null);
    assert.doesNotThrow(() => mouth.destroy());
  }
});
