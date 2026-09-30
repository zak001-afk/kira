import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { I18n, TRANSLATIONS, interfaceLanguage } from "../ui/i18n.mjs";
import { speechLocale, baseLanguage, matchingVoice } from "../ui/locale.mjs";
import { playerRig } from "./support/speech-fakes.mjs";

const french = { lang: "fr-FR", name: "Microsoft Denise" };
const english = { lang: "en-US", name: "Microsoft Zira", default: true };

test("all interface messages have French and Arabic translations", () => {
  assert.ok(Object.keys(TRANSLATIONS).length > 200);
  for (const [key, value] of Object.entries(TRANSLATIONS)) {
    assert.ok(value.fr, `missing French: ${key}`);
    assert.ok(value.ar, `missing Arabic: ${key}`);
    const variables = text => [...text.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort();
    assert.deepEqual(variables(value.fr), variables(key));
    assert.deepEqual(variables(value.ar), variables(key));
  }
});

test("interface language is independent of response content and speech locale", () => {
  const ui = new I18n("fr-FR");
  assert.equal(ui.t("SETTINGS"), "PARAMÈTRES");
  assert.equal(ui.t("A model response that is not a UI label"), "A model response that is not a UI label");
  assert.equal(ui.t("Current reply language: {language}", { language: "日本語" }), "Langue actuelle des réponses : 日本語");
  ui.setLanguage("ar");
  assert.equal(ui.t("SETTINGS"), "الإعدادات");
  assert.equal(interfaceLanguage("xx"), "en");
  assert.equal(speechLocale("fr"), "fr-FR");
  assert.equal(speechLocale("ja"), "ja-JP");
  assert.equal(speechLocale("ar-SA"), "ar-SA");
  assert.equal(speechLocale("not a language"), "en-US");
  assert.equal(baseLanguage("fr-CA"), "fr");
});

test("voice selection prefers the exact language and never the English default", () => {
  assert.equal(matchingVoice([english, { lang: "fr-CA", name: "French Canada" }, french], "fr-FR"), french);
  assert.equal(matchingVoice([english], "fr-FR"), null);
  assert.equal(matchingVoice([{ lang: "fr-CA", name: "French Canada" }], "fr-FR").lang, "fr-CA");
});

test("a spoken reply captures its language before the asynchronous TTS request", async () => {
  const rig = playerRig();
  await rig.player.speak("Bonjour, je suis Kira.", { language: "fr" });
  assert.equal(rig.fetches[0].language, "fr-FR");
  assert.equal(rig.player.session.language, "fr-FR");
  await rig.player.speak("مرحبا", { language: "ar" });
  assert.equal(rig.fetches[1].language, "ar-SA");
  assert.equal(rig.player.session.language, "ar-SA");
});

test("browser fallback sets both the utterance language and a matching voice", async () => {
  const rig = playerRig({ voices: [english, french], fetchAudio: async () => ({ error: "neural voice offline" }) });
  await rig.player.speak("Bonjour", { language: "fr-FR" });
  assert.equal(rig.utterances.length, 1);
  assert.equal(rig.utterances[0].lang, "fr-FR");
  assert.equal(rig.utterances[0].voice, french);
  assert.equal(rig.player.motion.mode, "browser");
});

test("missing French voices keep text available instead of reading through Zira", async () => {
  const rig = playerRig({ voices: [english], fetchAudio: async () => ({ error: "offline" }) });
  await rig.player.speak("Bonjour", { language: "fr" });
  assert.equal(rig.utterances.length, 0);
  assert.equal(rig.player.session, null);
  assert.equal(rig.player.motion.mode, null);
  assert.deepEqual(rig.notices, [{ code: "voice-unavailable", language: "fr-FR" }]);
});

test("late voice catalogs are handled once and listeners are released", async () => {
  const rig = playerRig({ voices: [], delayedVoices: true, fetchAudio: async () => ({ error: "offline" }) });
  await rig.player.speak("Bonjour", { language: "fr" });
  assert.equal(rig.utterances.length, 0);
  assert.equal(rig.voiceListeners.size, 1);
  rig.setVoices([english, french]);
  assert.equal(rig.utterances.length, 1);
  assert.equal(rig.utterances[0].voice, french);
  assert.equal(rig.voiceListeners.size, 0);
  rig.setVoices([english, french]);
  assert.equal(rig.utterances.length, 1);
});

test("mute cancels a pending voice catalog and no stale catalog can speak", async () => {
  const rig = playerRig({ voices: [], delayedVoices: true, fetchAudio: async () => ({ error: "offline" }) });
  await rig.player.speak("Bonjour", { language: "fr" });
  rig.player.setEnabled(false);
  assert.equal(rig.voiceListeners.size, 0);
  assert.equal(rig.timers.size, 0);
  rig.setVoices([french]);
  assert.equal(rig.utterances.length, 0);
});

test("playback fades in and schedules its end fade so no click is audible", async () => {
  const rig = playerRig();
  await rig.player.speak("Bonjour", { language: "fr" });
  const gain = rig.player.session?.gain;
  assert.ok(gain, "a running Web Audio graph must expose the anti-click gain");
  assert.deepEqual(gain.schedule, ["set", "ramp"], "playback must fade in, never start at full amplitude");
  rig.audios[0].duration = 2;
  rig.audios[0].onplaying();
  assert.deepEqual(gain.schedule, ["set", "ramp", "set", "ramp"], "the clip's final milliseconds must fade out on the audio clock");
  rig.audios[0].onended();
  assert.ok(rig.audios[0].loaded, "ending still releases the media immediately");
  assert.equal(rig.player.session, null);
  assert.deepEqual(rig.states.at(-1), "READY");
  assert.equal(rig.timers.size, 0, "no deferred teardown timer may outlive the reply");
});

test("a replaced session tears down instantly and cannot replay stale audio", async () => {
  const rig = playerRig();
  await rig.player.speak("Une phrase", { language: "fr" });
  const gain = rig.player.session.gain;
  await rig.player.speak("Une autre phrase", { language: "fr" });
  assert.ok(rig.audios[0].loaded, "an aborted session releases its media immediately");
  assert.equal(gain.schedule.includes("ramp"), true, "the old gain had its fade-in envelope");
  assert.equal(rig.player.session === null, false, "the new session keeps playing");
  rig.audios[1].onended();
  rig.fireTimers();
  assert.equal(rig.player.session, null);
});

test("missing voices have a deadline and do not leave the avatar talking", async () => {
  const rig = playerRig({ voices: [], delayedVoices: true, fetchAudio: async () => ({ error: "offline" }) });
  await rig.player.speak("Bonjour", { language: "fr" });
  rig.fireTimers();
  assert.equal(rig.voiceListeners.size, 0);
  assert.equal(rig.player.session, null);
  assert.equal(rig.player.motion.mode, null);
  assert.equal(rig.notices[0].language, "fr-FR");
});

test("MED interface remains French with its voice preferences", () => {
  const html = readFileSync(new URL("../ui/index.html", import.meta.url), "utf8");
  const app = readFileSync(new URL("../ui/app.js", import.meta.url), "utf8");
  assert.match(html, /<html lang="fr">/);
  assert.match(app, /kira\.voice/);
  assert.match(app, /voice: currentVoice\(\)/);
});
