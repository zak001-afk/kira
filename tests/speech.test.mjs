import test from "node:test";
import assert from "node:assert/strict";
import { SpeechMotion, cleanForSpeech } from "../ui/speech.mjs";

import { analyser, playerRig } from "./support/speech-fakes.mjs";

function motionRig() {
  let now = 0;
  const motion = new SpeechMotion(() => now);
  return { motion, advance(ms = 100) { now += ms; return { ...motion.sample() }; } };
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test("silence stays still; louder audio drives a stronger bounded envelope", () => {
  const { motion, advance } = motionRig();
  motion.startAudio(analyser(), { currentTime: 0 }, "hello");
  assert.equal(advance().energy, 0);
  motion.startAudio(analyser(8, 60, 40), { currentTime: 0 }, "hello");
  const quiet = advance().energy;
  motion.startAudio(analyser(40, 200, 180), { currentTime: 0 }, "hello");
  const loud = advance().energy;
  assert.ok(quiet > 0 && loud > quiet && loud <= 1);
});

test("bass and treble react to different audio frequency bands", () => {
  const a = motionRig(), b = motionRig();
  a.motion.startAudio(analyser(30, 240, 0), { currentTime: 0 }, "a");
  b.motion.startAudio(analyser(30, 0, 240), { currentTime: 0 }, "b");
  const bass = a.advance(), treble = b.advance();
  assert.ok(bass.low > treble.low);
  assert.ok(treble.high > bass.high);
});

test("speech envelopes attack smoothly and release to zero after ending", () => {
  const { motion, advance } = motionRig();
  motion.startAudio(analyser(30), { currentTime: 0 }, "hello");
  const one = advance(16).energy, two = advance(16).energy;
  assert.ok(one > 0 && two > one && two < 1);
  motion.stop();
  assert.ok(advance(16).energy < two);
  for (let i = 0; i < 25; i++) advance();
  assert.equal(advance().energy, 0);
});

test("pause fades to idle, resume follows sound again", () => {
  const { motion, advance } = motionRig();
  motion.startAudio(analyser(30), { currentTime: 0 }, "hello");
  advance();
  motion.pause();
  for (let i = 0; i < 25; i++) advance();
  assert.equal(advance().energy, 0);
  motion.resume();
  assert.ok(advance().energy > 0);
});

test("without Web Audio, motion follows media time, not elapsed fetch time", () => {
  const { motion, advance } = motionRig();
  const audio = { currentTime: 0 };
  motion.startAudio(null, audio, "hello world");
  assert.equal(advance(5000).energy, 0);
  audio.currentTime = 0.12;
  assert.ok(advance().energy > 0);
});

test("browser word boundaries re-anchor estimated motion to the actual word", () => {
  const { motion, advance } = motionRig();
  motion.startBrowser("hello world");
  advance(4000);
  assert.equal(advance().energy, 0);
  motion.boundary(6);
  assert.ok(advance(100).energy > 0);
});

test("browser fallback has quiet sentence gaps and stops after its estimate", () => {
  const { motion, advance } = motionRig();
  motion.startBrowser("Hi. Next.");
  assert.ok(advance(100).energy > 0);
  advance(100);
  const pause = advance(200).energy;
  assert.ok(pause < 0.65);
  for (let i = 0; i < 40; i++) advance();
  assert.equal(advance().energy, 0);
});

test("browser pause time does not skip ahead through the words", () => {
  const { motion, advance } = motionRig();
  motion.startBrowser("longer words here");
  advance(50);
  motion.pause();
  advance(5000);
  motion.resume();
  assert.ok(advance(50).energy > 0);
});

test("cleaning is shared by audio and estimated word timing", () => {
  assert.equal(cleanForSpeech("**Hello** https://example.com `secret`"), "Hello link");
  assert.equal(cleanForSpeech("```js\nhi\n```"), "code block");
});

test("motion starts on playback, not while waiting for TTS", async () => {
  const pending = deferred();
  const rig = playerRig({ fetchAudio: () => pending.promise });
  const request = rig.player.speak("hello");
  assert.equal(rig.states.at(-1), "THINKING");
  assert.equal(rig.advance().energy, 0);
  pending.resolve({ audio: "YWJj" });
  await request;
  assert.equal(rig.states.at(-1), "SPEAKING");
  assert.ok(rig.advance().energy > 0);
  rig.audios[0].onended();
  assert.equal(rig.states.at(-1), "READY");
  assert.equal(rig.revoked.length, 1);
  assert.ok(rig.contexts[0].nodes.every((node) => node.disconnected));
  assert.equal(rig.timers.size, 0);
});

test("muting aborts pending TTS and a late response cannot speak", async () => {
  const pending = deferred();
  const rig = playerRig({ fetchAudio: () => pending.promise });
  const request = rig.player.speak("hello");
  rig.player.setEnabled(false);
  assert.ok(rig.fetches[0].signal.aborted);
  pending.resolve({ audio: "YWJj" });
  await request;
  assert.equal(rig.audios.length, 0);
  assert.equal(rig.utterances.length, 0);
  assert.equal(rig.states.at(-1), "READY");
});

test("muting playing audio stops it and revokes its object URL", async () => {
  const rig = playerRig();
  await rig.player.speak("hello");
  rig.player.setEnabled(false);
  assert.ok(rig.audios[0].paused);
  assert.equal(rig.audios[0].src, "");
  assert.equal(rig.revoked.length, 1);
  assert.equal(rig.player.motion.mode, null);
  await rig.player.speak("do not play");
  assert.equal(rig.audios.length, 1);
});

test("late fetch results cannot interrupt a newer reply", async () => {
  const first = deferred(), second = deferred();
  const rig = playerRig({ fetchAudio: (text) => text === "old" ? first.promise : second.promise });
  const a = rig.player.speak("old"), b = rig.player.speak("new");
  second.resolve({ audio: "YWJj" });
  await b;
  first.resolve({ audio: "YWJj" });
  await a;
  assert.equal(rig.audios.length, 1);
  assert.equal(rig.states.at(-1), "SPEAKING");
});

test("stale media callbacks do not finish a newer reply", async () => {
  const rig = playerRig();
  await rig.player.speak("first");
  const ended = rig.audios[0].onended;
  await rig.player.speak("second");
  ended();
  assert.equal(rig.states.at(-1), "SPEAKING");
  assert.ok(!rig.audios[1].paused);
  assert.equal(rig.revoked.length, 1);
  assert.equal(rig.contexts.length, 1, "reuse one AudioContext across replies");
});

test("failed TTS uses word boundaries and mute cancels browser speech too", async () => {
  const rig = playerRig({ fetchAudio: async () => ({ error: "offline" }) });
  await rig.player.speak("hello world");
  assert.equal(rig.utterances.length, 1);
  assert.equal(rig.player.motion.mode, "browser");
  rig.advance(4000);
  rig.utterances[0].onboundary({ name: "word", charIndex: 6 });
  assert.ok(rig.advance(100).energy > 0);
  rig.player.setEnabled(false);
  assert.equal(rig.cancelled, 1);
  assert.equal(rig.states.at(-1), "READY");
});

test("browser speech events and stale cancellations are isolated per reply", async () => {
  const rig = playerRig({ fetchAudio: async () => ({ error: "offline" }) });
  await rig.player.speak("first words");
  const old = rig.utterances[0];
  old.onpause();
  assert.equal(rig.player.motion.paused, true);
  old.onresume();
  assert.equal(rig.player.motion.paused, false);
  await rig.player.speak("second words");
  old.onerror();
  old.onstart();
  assert.equal(rig.states.at(-1), "SPEAKING");
  assert.equal(rig.player.motion.mode, "browser");
});

test("audio failure and play rejection only trigger one fallback", async () => {
  const play = deferred();
  const rig = playerRig({ playPromise: play.promise });
  const request = rig.player.speak("hello");
  await Promise.resolve();
  const staleEnded = rig.audios[0].onended;
  rig.audios[0].onerror();
  staleEnded(); // a queued media event must not stop the browser fallback
  assert.equal(rig.states.at(-1), "SPEAKING");
  play.reject(new Error("decode failed"));
  await request;
  assert.equal(rig.utterances.length, 1);
  assert.equal(rig.revoked.length, 1);
});

test("rejected autoplay falls back without leaving phantom motion", async () => {
  const rig = playerRig({ playReject: true, noSynth: true });
  await rig.player.speak("hello");
  assert.equal(rig.states.at(-1), "READY");
  assert.equal(rig.player.motion.mode, null);
  assert.equal(rig.revoked.length, 1);
});

test("a TTS timeout falls back; even an abort-ignoring fetch cannot replay", async () => {
  const pending = deferred();
  const rig = playerRig({ fetchAudio: () => pending.promise });
  const request = rig.player.speak("hello");
  rig.fireTimers();
  assert.ok(rig.fetches[0].signal.aborted);
  assert.equal(rig.utterances.length, 1);
  pending.resolve({ audio: "YWJj" });
  await request;
  assert.equal(rig.audios.length, 0);
});

test("a browser voice that never starts times out to idle", async () => {
  const rig = playerRig({ fetchAudio: async () => ({}), noStart: true });
  await rig.player.speak("hello");
  assert.equal(rig.player.motion.mode, null);
  rig.fireTimers();
  assert.equal(rig.states.at(-1), "READY");
  assert.equal(rig.player.session, null);
});

test("no Web Audio or a suspended context leaves audio on the normal path", async () => {
  for (const options of [{ noContext: true }, { suspended: true }, { graphFail: true }]) {
    const rig = playerRig(options);
    await rig.player.speak("hello");
    assert.equal(rig.player.session.analyser || null, null);
    assert.equal(rig.states.at(-1), "SPEAKING");
    rig.audios[0].currentTime = 0.12;
    assert.ok(rig.advance().energy > 0);
  }
});

test("buffering quiets the animation and playing resumes it", async () => {
  const rig = playerRig();
  await rig.player.speak("hello");
  rig.advance();
  rig.audios[0].onwaiting();
  assert.equal(rig.player.motion.paused, true);
  rig.audios[0].onplaying();
  assert.equal(rig.player.motion.paused, false);
  assert.equal(rig.states.at(-1), "SPEAKING");
});

test("closing the page releases audio nodes, URLs, timers and the context", async () => {
  const rig = playerRig();
  await rig.player.speak("hello");
  rig.player.destroy();
  assert.equal(rig.contexts[0].state, "closed");
  assert.equal(rig.player.context, null);
  assert.equal(rig.revoked.length, 1);
  assert.equal(rig.timers.size, 0);
  assert.equal(rig.player.session, null);
});
