import test from "node:test";
import assert from "node:assert/strict";
import { VoiceQueue, localSentences, paceGapMs } from "../ui/voice_queue.mjs";

// A fake SpeechPlayer: records speak() calls and lets the test end a clip,
// exactly like the real player's onState("READY") after audio ends.
class FakePlayer {
  constructor() {
    this.enabled = true;
    this.onState = () => {};
    this.calls = [];
    this.stopped = 0;
  }
  speak(text, options = {}) {
    this.calls.push({ text, options });
    this.onState("THINKING");
    return Promise.resolve().then(() => this.onState("SPEAKING"));
  }
  end() { this.onState("READY"); }
  stop() { this.stopped++; }
}

function rig({ plan = ["Alpha.", "Beta."], failPlan = false, gapMs = 0 } = {}) {
  const player = new FakePlayer();
  const requests = [];
  const states = [];
  const notices = [];
  const fetchImpl = async (url, init) => {
    const body = init?.body ? JSON.parse(init.body) : null;
    requests.push({ url, body });
    if (url.endsWith("/plan")) {
      if (failPlan) throw new Error("offline");
      const sentences = typeof plan === "function" ? plan(body.text) : plan;
      return { ok: true, json: async () => ({ sentences }) };
    }
    return { ok: true, json: async () => ({ audio: "YWJj" }) };
  };
  const queue = new VoiceQueue({
    player, apiBase: "", fetchImpl, gapMs,
    onState: state => states.push(state), onNotice: n => notices.push(n),
  });
  const tick = () => new Promise(resolve => setImmediate(resolve));
  return { player, queue, requests, states, notices, tick };
}

test("sentences are planned once and played strictly one at a time", async () => {
  const { player, queue, requests, tick } = rig();
  await queue.speak("Alpha. Beta.", { language: "en-US" });
  await tick();
  assert.equal(requests[0].url, "/api/tts/plan");
  assert.equal(requests[0].body.mode, "normal");
  assert.deepEqual(player.calls.map(call => call.text), ["Alpha."]);
  player.end();
  await tick();
  assert.deepEqual(player.calls.map(call => call.text), ["Alpha.", "Beta."]);
  player.end();
  await tick();
  assert.equal(queue.speaking, false);
});

test("stop() aborts the current clip and drops everything still queued", async () => {
  const { player, queue, states, tick } = rig({ plan: ["One.", "Two.", "Three."] });
  await queue.speak("One. Two. Three.");
  await tick();
  assert.deepEqual(player.calls.map(call => call.text), ["One."]);
  player.stopped = 0; // speak()'s initial cleanup already stopped the idle player
  queue.stop();
  player.end();
  await tick();
  assert.deepEqual(player.calls.map(call => call.text), ["One."]);
  assert.equal(player.stopped, 1);
  assert.ok(states.includes("INTERRUPTED"));
});

test("a new reply replaces the old one without overlapping audio", async () => {
  const plan = text => (text.startsWith("Old") ? ["Old one.", "Old two."] : ["New reply."]);
  const { player, queue, tick } = rig({ plan });
  await queue.speak("Old one. Old two.");
  await tick();
  player.stopped = 0;
  await queue.speak("New reply.");
  await tick();
  assert.deepEqual(player.calls.map(call => call.text), ["Old one.", "New reply."]);
  assert.equal(player.stopped, 1);
});

test("when the plan endpoint fails the reply is split locally and capped", async () => {
  const { player, queue, tick } = rig({ failPlan: true });
  await queue.speak("One. Two. Three. Four. Five. Six.");
  await tick();
  assert.deepEqual(player.calls.map(call => call.text), ["One."]);
  for (let clip = 0; clip < 3; clip++) {
    player.end();
    await tick();
  }
  assert.deepEqual(player.calls.map(call => call.text), ["One.", "Two.", "Three.", "Four."]);
  player.end();
  await tick();
  assert.equal(player.calls.length, 4); // Five and Six were capped out
});

test("single-sentence replies keep the player's progress callback untouched", async () => {
  const { player, queue, tick } = rig({ plan: ["Only one sentence."] });
  const seen = [];
  await queue.speak("Only one sentence.", { onProgress: value => seen.push(value) });
  await tick();
  assert.equal(player.calls.length, 1);
  player.calls[0].options.onProgress(5);
  assert.deepEqual(seen, [5]);
});

test("multi-clip progress is remapped onto the full reply proportionally", async () => {
  const { player, queue, tick } = rig({ plan: ["Alpha.", "Beta."] });
  const seen = [];
  await queue.speak("Alpha. Beta.", { onProgress: value => seen.push(value) });
  await tick();
  player.calls[0].options.onProgress(3);
  player.end();
  await tick();
  player.calls[1].options.onProgress(2);
  const [first, second] = seen;
  assert.ok(first > 0 && first <= 12);
  assert.ok(second > first && second <= 12);
});

test("READY between clips is suppressed so the orb stays in SPEAKING", async () => {
  const { player, queue, states, tick } = rig();
  await queue.speak("Alpha. Beta.");
  await tick();
  player.end(); // end of the first clip, one more queued
  await tick();
  assert.equal(states.at(-1), "SPEAKING");
  player.end(); // end of the last clip
  await tick();
  assert.equal(states.at(-1), "READY");
});

test("the pause between sentences follows the speaking mode", async () => {
  assert.equal(paceGapMs(undefined, undefined), 340);          // normal, no profile yet
  assert.equal(paceGapMs({ sentence_pause: 0.45 }, undefined), 340);  // normal
  assert.equal(paceGapMs({ sentence_pause: 0.6 }, undefined), 490);   // serious / system
  assert.equal(paceGapMs({ sentence_pause: 0.14 }, undefined), 120);  // alert, floored
  assert.equal(paceGapMs({ sentence_pause: 5 }, undefined), 700);     // clamped
  assert.equal(paceGapMs({ sentence_pause: 0.6 }, 0), 0);             // explicit override

  // The session uses the profile the plan endpoint returned.
  const player = new FakePlayer();
  const fetchImpl = async url => ({
    ok: true,
    json: async () => (url.endsWith("/plan")
      ? { sentences: ["Alpha.", "Beta."], profile: { sentence_pause: 0.6 } }
      : { audio: "YWJj" }),
  });
  const queue = new VoiceQueue({ player, apiBase: "", fetchImpl });
  await queue.speak("Alpha. Beta.");
  assert.equal(queue.session.gap, 490);
  queue.stop();
});

test("localSentences splits, cleans and caps written replies", () => {
  assert.deepEqual(localSentences("Hello there. How are you?"), ["Hello there.", "How are you?"]);
  // cleanForSpeech drops inline code content on purpose: never read code aloud.
  assert.deepEqual(localSentences("**Bold.** `code` here."), ["Bold.", "here."]);
  assert.equal(localSentences("One. Two. Three. Four. Five.").length, 4);
  assert.deepEqual(localSentences(""), []);
});
