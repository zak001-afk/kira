"""One command/reply path for native, web and HTTP clients.

Language selection is per request, not global. Conversational replies are not
cached across turns/languages; desktop actions are never retried for translation.
"""
from datetime import datetime
import inspect
import re
import kira_language as languages


_MESSAGES = {
    "greeting": {
        "en": "Hello! I’m KIRA. How can I help you?", "fr": "Bonjour ! Je suis KIRA. Comment puis-je vous aider ?",
        "ar": "مرحباً! أنا كيرا. كيف يمكنني مساعدتك؟", "es": "¡Hola! Soy KIRA. ¿En qué puedo ayudarte?",
        "de": "Hallo! Ich bin KIRA. Wie kann ich dir helfen?", "it": "Ciao! Sono KIRA. Come posso aiutarti?",
        "pt": "Olá! Sou a KIRA. Como posso ajudar?", "ru": "Здравствуйте! Я КИРА. Чем могу помочь?",
        "uk": "Вітаю! Я КІРА. Чим можу допомогти?", "zh": "你好！我是 KIRA。有什么可以帮你的吗？",
        "ja": "こんにちは！KIRAです。何をお手伝いしましょうか？", "ko": "안녕하세요! KIRA입니다. 무엇을 도와드릴까요?",
        "hi": "नमस्ते! मैं KIRA हूँ। मैं आपकी क्या सहायता कर सकती हूँ?", "tr": "Merhaba! Ben KIRA. Nasıl yardımcı olabilirim?",
        "nl": "Hallo! Ik ben KIRA. Hoe kan ik je helpen?",
    },
    "thanks": {"en": "You’re welcome!", "fr": "Avec plaisir !", "ar": "على الرحب والسعة!", "es": "¡De nada!", "de": "Gern geschehen!", "it": "Prego!", "pt": "De nada!", "zh": "不客气！", "ja": "どういたしまして！", "ru": "Пожалуйста!"},
    "identity": {"en": "I’m KIRA, your local AI assistant. I can chat, manage tasks and use the computer controls connected to this application.", "fr": "Je suis KIRA, votre assistante IA locale. Je peux discuter, gérer vos tâches et utiliser les commandes de votre ordinateur reliées à cette application.", "ar": "أنا كيرا، مساعدتك المحلية بالذكاء الاصطناعي. يمكنني المحادثة وإدارة المهام واستخدام أدوات التحكم بالحاسوب المتصلة بهذا التطبيق."},
    "help": {"en": "You can ask me questions, open applications, search the web, manage tasks or analyze your screen. Available actions depend on the connected KIRA backend.", "fr": "Vous pouvez me poser des questions, ouvrir des applications, rechercher sur le Web, gérer vos tâches ou analyser votre écran. Les actions disponibles dépendent du moteur KIRA connecté.", "ar": "يمكنك طرح الأسئلة وفتح التطبيقات والبحث في الويب وإدارة المهام أو تحليل الشاشة. تعتمد الإجراءات المتاحة على محرك كيرا المتصل."},
    "time": {"en": "It is {value}.", "fr": "Il est {value}.", "ar": "الساعة الآن {value}.", "es": "Son las {value}.", "de": "Es ist {value} Uhr."},
    "date": {"en": "Today is {value}.", "fr": "Nous sommes le {value}.", "ar": "تاريخ اليوم هو {value}.", "es": "Hoy es {value}.", "de": "Heute ist der {value}."},
    "language": {
        "en": "I’ll reply in English, both in writing and aloud when an English voice is available.",
        "fr": "D’accord, je vous répondrai en français, à l’écrit et à l’oral si une voix française est disponible.",
        "ar": "حسناً، سأجيبك بالعربية كتابةً وصوتاً عند توفر صوت عربي.",
        "es": "Te responderé en español, por escrito y con voz cuando haya una voz española disponible.",
        "de": "Ich antworte auf Deutsch, schriftlich und mit einer verfügbaren deutschen Stimme.",
        "it": "Ti risponderò in italiano, per iscritto e con una voce italiana disponibile.",
        "pt": "Vou responder em português, por escrito e com uma voz em português disponível.",
        "ru": "Я буду отвечать по-русски, письменно и вслух, если доступен русский голос.",
        "zh": "好的，我会用中文回复；有可用的中文语音时也会朗读。",
        "ja": "日本語でお答えします。日本語の音声が利用できる場合は読み上げます。",
    },
    "auto": {"en": "Automatic language selection is enabled. I’ll follow the language of your questions.", "fr": "La langue automatique est activée. Je suivrai la langue de vos questions.", "ar": "تم تفعيل اختيار اللغة تلقائياً. سأتبع لغة أسئلتك."},
    "action_failed": {"en": "I could not complete that action.", "fr": "Je n’ai pas pu effectuer cette action.", "ar": "لم أتمكن من تنفيذ هذا الإجراء."},
    "model_offline": {"en": "I cannot reach the local AI model. Start Ollama with ollama serve, then try again.", "fr": "Je ne peux pas joindre le modèle IA local. Démarrez Ollama avec ollama serve, puis réessayez.", "ar": "لا أستطيع الاتصال بنموذج الذكاء الاصطناعي المحلي. شغّل Ollama بالأمر ollama serve ثم حاول مجدداً."},
    "wrong_language": {"en": "The model could not answer in the requested language. Try a multilingual model or another language.", "fr": "Le modèle n’a pas réussi à répondre dans la langue demandée. Essayez un modèle multilingue ou une autre langue.", "ar": "لم يتمكن النموذج من الإجابة باللغة المطلوبة. جرّب نموذجاً متعدد اللغات أو لغة أخرى."},
}


def message(key, language, **values):
    text = _MESSAGES.get(key, {}).get(languages.normalize_language(language))
    return text.format(**values) if text else None


def builtin_reply(text, language):
    normalized = languages.fold(text).strip(" .!?؟,،;")
    key, values = None, {}
    if normalized in languages.GREETING_LANGUAGES:
        key = "greeting"
    elif normalized in {"thanks", "thank you", "merci", "merci beaucoup", "شكرا", "gracias", "danke", "grazie", "obrigado", "obrigada", "谢谢", "ありがとう", "спасибо"}:
        key = "thanks"
    elif normalized in {"who are you", "what are you", "what is kira", "qui es tu", "qui es-tu", "qui etes vous", "qui etes-vous", "tu es qui", "من انت"}:
        key = "identity"
    elif normalized in {"help", "commands", "what can you do", "aide", "commandes", "que peux tu faire", "que peux-tu faire", "مساعدة", "ماذا يمكنك ان تفعل"}:
        key = "help"
    elif normalized in {"what time is it", "time", "current time", "quelle heure est il", "quelle heure est-il", "il est quelle heure", "heure", "كم الساعة"}:
        key, values = "time", {"value": datetime.now().strftime("%H:%M")}
    elif normalized in {"what is the date", "today's date", "date", "what day is it", "quelle est la date", "date du jour", "تاريخ اليوم"}:
        key, values = "date", {"value": datetime.now().strftime("%d/%m/%Y")}
    # No English fallback: unsupported canned replies go to the multilingual model.
    return message(key, language, **values) if key else None


def call_with_options(callback, text, **options):
    """Preserve older text-only integrations without ever invoking them twice."""
    try:
        params = inspect.signature(callback).parameters
        accepts_all = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        kwargs = {key: value for key, value in options.items() if accepts_all or key in params}
    except (ValueError, TypeError):
        kwargs = {}
    return callback(text, **kwargs)


def process_command(backend, text, reply_language="auto", previous_language=None, interface_language="en", chat_only=False):
    text = str(text or "").strip()
    choice = languages.resolve_reply_language(text, reply_language, previous_language, interface_language)
    metadata = choice.metadata()
    if backend is None:
        return {"error": "Backend not available", "error_code": "backend_unavailable", **metadata}
    if not text:
        return {"action": "none", "response": "", **metadata}
    if choice.language_only:
        reply = message("auto" if choice.preference == "auto" else "language", choice.language)
        return {"action": "language", "response": reply or languages.LANGUAGES[choice.language]["native_name"] + " ✓", **metadata}
    try:
        canned = builtin_reply(text, choice.language)
        if canned:
            return {"action": "chat", "response": canned, **metadata}
        cleaned = backend.normalize_command(text)
        if not cleaned:
            return {"action": "none", "response": "", **metadata}
        parsed = None if chat_only else backend.parse_simple_command(cleaned)
        if parsed and parsed.get("action", "none") != "none":
            action = parsed["action"]
            success = backend.execute_action(parsed)  # Exactly once, before any translation.
            if not success:
                reply = message("action_failed", choice.language) or message("action_failed", "en")
            elif hasattr(backend, "build_reply"):
                reply = backend.build_reply(choice.language, action, str(parsed.get("target", parsed.get("query", ""))))
            else:
                reply = backend.describe_action(parsed)
            try:
                if hasattr(backend, "call_ollama"):
                    reply = languages.ensure_reply_language(reply, choice.language, backend.call_ollama)
            except languages.ReplyLanguageError:
                # Do not encourage a user to repeat an action that already ran.
                return {"action": action, "success": bool(success), "response": message("wrong_language", interface_language) or message("wrong_language", "en"),
                        "language_warning": "action_completed_translation_unavailable" if success else "action_failed_translation_unavailable", **metadata}
            return {"action": action, "success": bool(success), "response": reply, **metadata}
        answer = call_with_options(backend.ask_chat, cleaned, language=choice.language)
        return {"action": "chat", "response": answer, **metadata}
    except languages.ReplyLanguageError:
        return {"error": message("wrong_language", interface_language) or message("wrong_language", "en"), "error_code": "reply_language_unavailable", **metadata}
    except Exception as error:
        return {"error": str(error), "error_code": "command_failed", **metadata}
