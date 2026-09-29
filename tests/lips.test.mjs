import test from "node:test";
import assert from "node:assert/strict";
import { LipMotion, VisemeTimeline, VISEMES, REST_MOUTH, wordCues, lipDemoPose } from "../ui/lips.mjs";
import { createMouthMesh, deformMouth, fitMouthRegion, MOUTH_REGION } from "../ui/mouth.mjs";
import { SpeechMotion } from "../ui/speech.mjs";
import { analyser, playerRig } from "./support/speech-fakes.mjs";

const timed = (text, start = 0, duration = 1) => new VisemeTimeline(text, { timings: [{ text, start, duration }] });
const voice = (mouth, level = 0.6) => ({ active: true, energy: level, level, mouth });

test("hello has different estimated H, E, L and rounded O shapes", () => {
  assert.deepEqual(wordCues("Hello").map(cue => cue.viseme), ["H", "EE", "LL", "OH"]);
  const timeline = timed("Hello");
  const vowel = timeline.sample(350), rounded = timeline.sample(800);
  assert.equal(vowel.viseme, "EE");
  assert.ok(vowel.wide > 0.8);
  assert.equal(rounded.viseme, "OH");
  assert.ok(rounded.round > 0.6);
});

test("bilabials close the lips, fricatives bite, vowels open or round", () => {
  assert.ok(wordCues("papa maman bébé").some(cue => cue.viseme === "MBP"));
  assert.equal(wordCues("f")[0].viseme, "FV");
  assert.equal(wordCues("ou")[0].viseme, "OO");
  assert.equal(wordCues("م")[0].viseme, "MBP");
  assert.equal(wordCues("و")[0].viseme, "OO");
  const mouth = new LipMotion();
  for (let i = 0; i < 10; i++) mouth.sample(voice({ ...VISEMES.MBP, viseme: "MBP" }), { now: i * 33 });
  assert.equal(mouth.pose.open, 0);
  assert.ok(mouth.pose.press > 0.95, "a loud P must not become an open jaw");
});

test("real word timestamps include leading silence and between-word pauses", () => {
  const timeline = new VisemeTimeline("Hello. Bonjour.", { timings: [
    { text: "Hello", start: 0.25, duration: 0.8 },
    { text: "Bonjour", start: 1.8, duration: 0.9 },
  ] });
  assert.equal(timeline.sample(100).open, 0);
  assert.ok(timeline.sample(600).open > 0);
  assert.equal(timeline.sample(1400).open, 0);
  assert.equal(timeline.sample(6000, { keepAlive: true }).open, 0, "measured timing must not loop");
  assert.equal(timeline.sample(600).source, "word-timings");
});

test("invalid timing metadata falls back without NaN or exceptions", () => {
  for (const timings of [null, {}, [], [{ start: NaN, duration: 1, text: "Hello" }], [{ start: 0, duration: -1, text: "Hello" }]]) {
    const timeline = new VisemeTimeline("Hello", { timings });
    assert.equal(timeline.measured, false);
    const pose = timeline.sample(120);
    for (const key of ["open", "round", "wide", "bite", "press"]) assert.ok(Number.isFinite(pose[key]));
  }
  const timeline = new VisemeTimeline("Hello", { timings: [{ start: 0.1, duration: 0.6, text: "Hello" }, { start: 0, duration: 0.1, text: "out of order" }] });
  assert.equal(timeline.words.length, 1);
});

test("estimated visemes stretch to clip length, not the request start time", () => {
  const timeline = new VisemeTimeline("Hello");
  const short = timeline.sample(170, { duration: 260 });
  const long = timeline.sample(1700, { duration: 2600 });
  assert.equal(short.viseme, long.viseme);
  assert.ok(Math.abs(short.open - long.open) < 0.00001);
  assert.equal(timeline.sample(4000, { duration: 2600 }).open, 0);
});

test("the lips close on real silence even while the field envelope is releasing", () => {
  const motion = new LipMotion();
  for (let i = 0; i < 12; i++) motion.sample(voice({ ...VISEMES.AH, viseme: "AH" }), { now: i * 33 });
  assert.ok(motion.pose.open > 0.6);
  for (let i = 12; i < 24; i++) motion.sample({ ...voice(VISEMES.AH), level: 0, energy: 0.9 }, { now: i * 33 });
  assert.equal(motion.pose.open, 0, "silence must close the mouth, not continue a speech loop");
});

test("inactive, muted, reduced-motion and disabled lips have a neutral pose", () => {
  for (const option of [{ disabled: true }, { enabled: false }]) {
    const motion = new LipMotion();
    motion.sample(voice(VISEMES.AH), { now: 10 });
    assert.deepEqual(motion.sample(voice(VISEMES.OO), { now: 50, ...option }), { ...REST_MOUTH });
  }
  const motion = new LipMotion();
  motion.sample(voice(VISEMES.AH), { now: 10 });
  for (let i = 1; i < 20; i++) motion.sample({ ...voice(VISEMES.AH), active: false }, { now: 10 + i * 33 });
  assert.equal(motion.pose.open, 0);
});

test("the lip demo is bounded, finite, and checks several articulations", () => {
  assert.equal(lipDemoPose(-1), null);
  assert.equal(lipDemoPose(4.3), null);
  assert.equal(lipDemoPose(Infinity), null);
  const shapes = new Set([0.5, 1, 1.6, 2.2, 2.8, 3.4, 4].map(t => lipDemoPose(t).viseme));
  assert.deepEqual(shapes, new Set(["REST", "AH", "EE", "OO", "FV", "MBP"]));
});

test("neutral geometry is unchanged and speech deforms actual lip vertices", () => {
  const mesh = createMouthMesh();
  assert.deepEqual(deformMouth(REST_MOUTH), mesh.vertices);
  const opened = deformMouth(VISEMES.AH), rounded = deformMouth(VISEMES.OO);
  assert.ok(opened[17] > mesh.vertices[17] + 20, "lower lip must move, not just an overlay opacity");
  assert.ok(rounded[0] < mesh.vertices[0] - 20, "rounded vowel must pull corners inward");
  // The outer skin boundary is fixed, preventing a rectangular moving patch.
  for (let i = 32 * 3 * 2; i < opened.length; i++) assert.equal(opened[i], mesh.vertices[i]);
  for (const shape of [...Object.values(VISEMES), { open: NaN, round: Infinity, wide: -100 }]) {
    const points = deformMouth(shape);
    assert.ok([...points].every(Number.isFinite));
    for (let i = 0; i < points.length; i += 2) {
      assert.ok(points[i] >= -0.01 && points[i] <= MOUTH_REGION.width + 0.01);
      assert.ok(points[i + 1] >= -0.01 && points[i + 1] <= MOUTH_REGION.height + 0.01);
    }
  }
});

test("mouth positioning follows object-fit contain including letterboxing", () => {
  const original = fitMouthRegion(896, 1200);
  assert.deepEqual(original, { left: 296, top: 554, width: 304, height: 224 });
  const wide = fitMouthRegion(1000, 600);
  assert.equal(wide.left, (1000 - 448) / 2 + 148);
  assert.equal(wide.top, 277);
  const tall = fitMouthRegion(448, 800);
  assert.equal(tall.top, 100 + 277);
  assert.equal(tall.width, 152);
});

test("speech motion uses word timing at the media position, including silence", () => {
  let now = 0;
  const motion = new SpeechMotion(() => now);
  const media = { currentTime: 0, duration: 3 };
  motion.startAudio(analyser(25), media, "Hello.", [{ text: "Hello", start: 1, duration: 1 }]);
  now = 5000;
  assert.equal(motion.sample().mouth.open, 0, "wall-clock fetch time must not move the mouth");
  media.currentTime = 1.35; now += 100;
  assert.equal(motion.sample().mouth.viseme, "EE");
  motion.pause(); now += 100;
  assert.equal(motion.sample().mouth.open, 0);
  motion.resume(); media.currentTime = 1.8; now += 100;
  assert.equal(motion.sample().mouth.viseme, "OH");
  motion.stop(); now += 100;
  assert.equal(motion.sample().mouth.open, 0);
});

test("browser boundaries re-anchor shapes and pause/resume preserves their place", () => {
  let now = 0;
  const motion = new SpeechMotion(() => now);
  motion.startBrowser("Hello mama", 1);
  now = 3000; motion.boundary(6); now += 20;
  assert.equal(motion.sample().mouth.viseme, "MBP");
  assert.equal(motion.frame.mouth.source, "word-events");
  motion.pause(); now += 5000;
  assert.equal(motion.sample().mouth.open, 0);
  motion.resume(); now += 10;
  assert.equal(motion.sample().mouth.viseme, "MBP");
});

test("spoken text advances on the exact measured word boundaries", () => {
  const motion = new SpeechMotion(() => 0);
  const media = { currentTime: 0, duration: 2 };
  const progress = [];
  motion.startAudio(null, media, "Hello there.", [
    { text: "Hello", start: 0.25, duration: 0.4 },
    { text: "there", start: 0.9, duration: 0.5 },
  ]);
  motion.onProgress = value => progress.push(value);
  motion.sample();
  assert.equal(motion.frame.charIndex, 0, "leading silence keeps the caption waiting");
  media.currentTime = 0.3;
  motion.sample();
  assert.equal(motion.frame.charIndex, 5);
  media.currentTime = 1;
  motion.sample();
  assert.equal(motion.frame.charIndex, 12);
  assert.deepEqual(progress, [0, 5, 12]);
});

test("the real player forwards timing metadata and buffering does not rebuild it", async () => {
  const rig = playerRig({ fetchAudio: async () => ({ audio: "YWJj", word_timings: [{ text: "Hello", start: 0.3, duration: 1 }] }) });
  const captionProgress = [];
  await rig.player.speak("Hello", { onProgress: value => captionProgress.push(value) });
  const timeline = rig.player.motion.articulation;
  assert.equal(timeline.measured, true);
  rig.audios[0].onwaiting();
  rig.audios[0].currentTime = 0.7;
  rig.audios[0].onplaying();
  assert.equal(rig.player.motion.articulation, timeline, "buffering must not reset the lip clock");
  rig.advance();
  assert.equal(rig.player.motion.frame.mouth.viseme, "EE");
  assert.ok(captionProgress.includes(5), "caption callback follows the TTS word timestamp");
  rig.player.setEnabled(false);
  assert.equal(rig.player.motion.articulation, null);
  assert.equal(rig.player.motion.frame.mouth.open, 0);
});
