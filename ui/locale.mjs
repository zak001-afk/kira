// Speech locale helpers do not depend on the interface language or DOM.
const DEFAULTS = {
  en: "en-US", fr: "fr-FR", ar: "ar-SA", es: "es-ES", de: "de-DE", it: "it-IT",
  pt: "pt-BR", ru: "ru-RU", uk: "uk-UA", zh: "zh-CN", ja: "ja-JP", ko: "ko-KR",
  hi: "hi-IN", bn: "bn-IN", ta: "ta-IN", te: "te-IN", mr: "mr-IN", ur: "ur-PK",
  fa: "fa-IR", tr: "tr-TR", nl: "nl-NL", pl: "pl-PL", sv: "sv-SE", no: "nb-NO",
  nb: "nb-NO", da: "da-DK", fi: "fi-FI", cs: "cs-CZ", ro: "ro-RO", el: "el-GR",
  he: "he-IL", id: "id-ID", ms: "ms-MY", vi: "vi-VN", th: "th-TH", fil: "fil-PH",
};
export function baseLanguage(value) {
  const code = String(value || "").toLowerCase().replace(/_/g, "-").split("-")[0];
  return ({ nb: "no", nn: "no", tl: "fil", iw: "he", cmn: "zh" })[code] || code;
}
export function speechLocale(value, fallback = "en-US") {
  let locale = String(value || "").replace(/_/g, "-");
  if (!/^[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,3}$/i.test(locale)) return fallback;
  if (!locale.includes("-")) locale = DEFAULTS[locale.toLowerCase()] || locale;
  try { return Intl.getCanonicalLocales(locale)[0] || fallback; } catch { return fallback; }
}
// KIRA speaks with a female voice: a male browser/OS voice (David, Guy, Henri…)
// must never win over a neutral female one for the same language.
const MALE_VOICE = /\bmale\b|david|mark|george|richard|ryan|guy|christopher|steffan|henri|thomas|pierre|antoine|julien/i;
export function matchingVoice(voices, language) {
  const locale = speechLocale(language).toLowerCase();
  return (voices || []).filter(voice => baseLanguage(voice.lang) === baseLanguage(locale))
    .map((voice, index) => ({ voice, score:
      (String(voice.lang).replace(/_/g, "-").toLowerCase() === locale ? 20 : 0)
      + (/female|denise|hortense|samantha|zira|jenny|katja|elvira|nanami|xiaoxiao|zariyah/i.test(voice.name || "") ? 5 : 0)
      + (voice.default ? 1 : 0)
      - (MALE_VOICE.test(String(voice.name || "")) ? 10 : 0), index }))
    .sort((a, b) => b.score - a.score || a.index - b.index)[0]?.voice || null;
}
export const FALLBACK_LANGUAGES = [
  ["en", "English"], ["fr", "Français"], ["ar", "العربية"], ["es", "Español"],
  ["de", "Deutsch"], ["it", "Italiano"], ["pt", "Português"], ["ru", "Русский"],
  ["zh", "中文"], ["ja", "日本語"], ["ko", "한국어"], ["hi", "हिन्दी"],
].map(([code, native_name]) => ({ code, native_name, locale: speechLocale(code) }));
export const VOICE_SAMPLES = {
  en: "Hello. I am Kira. My voice and my written replies use English. How can I help you?",
  fr: "Bonjour. Je suis Kira. Je vous réponds en français, à l’écrit comme à l’oral. Comment puis-je vous aider ?",
  ar: "مرحباً. أنا كيرا. أجيبك بالعربية كتابةً وصوتاً. كيف يمكنني مساعدتك؟",
  es: "Hola. Soy Kira. Te respondo en español, por escrito y con voz. ¿En qué puedo ayudarte?",
  de: "Hallo. Ich bin Kira. Ich antworte auf Deutsch, schriftlich und mit meiner Stimme.",
  it: "Ciao. Sono Kira. Ti rispondo in italiano, sia per iscritto che a voce.",
  pt: "Olá. Sou a Kira. Respondo em português, por escrito e com voz.",
  ru: "Здравствуйте. Я Кира. Я отвечаю по-русски, письменно и вслух.",
  zh: "你好，我是基拉。我会用中文书写和朗读回复。有什么可以帮助你的吗？",
  ja: "こんにちは。キラです。日本語の文章と音声でお答えします。",
  ko: "안녕하세요. 키라입니다. 한국어로 글을 쓰고 말합니다.",
  hi: "नमस्ते। मैं किरा हूँ। मैं हिंदी में लिखकर और बोलकर उत्तर देती हूँ।",
};
