"""One command/reply path for native, web and HTTP clients.

Language selection is per request, not global. Conversational replies are not
cached across turns/languages; desktop actions are never retried for translation.
"""
from datetime import datetime
from pathlib import Path
import inspect
import re
import time as _time
import kira_language as languages
import kira_open


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
    "help": {"en": "You can ask me questions, open applications, files and web pages, search the web, manage tasks or analyze your screen. Available actions depend on the connected KIRA backend.", "fr": "Vous pouvez me poser des questions, ouvrir des applications, des fichiers et des pages web, rechercher sur le Web, gérer vos tâches ou analyser votre écran. Les actions disponibles dépendent du moteur KIRA connecté.", "ar": "يمكنك طرح الأسئلة وفتح التطبيقات والملفات وصفحات الويب والبحث في الويب وإدارة المهام أو تحليل الشاشة. تعتمد الإجراءات المتاحة على محرك كيرا المتصل."},
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
    "reminder_added": {"en": "Reminder added: {title}.", "fr": "Rappel ajouté : {title}.", "ar": "تمت إضافة التذكير: {title}."},
    "todo_added": {"en": "Todo added: {title}.", "fr": "Tâche ajoutée : {title}.", "ar": "تمت إضافة المهمة: {title}."},
    "task_title_missing": {"en": "What should the task say?", "fr": "Que dois-je noter ?", "ar": "ماذا أكتب في المهمة؟"},
    "tasks_none": {"en": "You have no pending tasks.", "fr": "Vous n’avez aucune tâche en attente.", "ar": "ليست لديك مهام معلقة."},
    "tasks_pending_one": {"en": "You have 1 pending task:\n{list}", "fr": "Vous avez 1 tâche en attente :\n{list}", "ar": "لديك مهمة واحدة معلقة:\n{list}"},
    "tasks_pending": {"en": "You have {count} pending tasks:\n{list}", "fr": "Vous avez {count} tâches en attente :\n{list}", "ar": "لديك {count} مهام معلقة:\n{list}"},
    "tasks_cleared_one": {"en": "Cleared 1 completed task.", "fr": "J’ai supprimé 1 tâche terminée.", "ar": "حذفت مهمة مكتملة واحدة."},
    "tasks_cleared": {"en": "Cleared {count} completed tasks.", "fr": "J’ai supprimé {count} tâches terminées.", "ar": "حذفت {count} مهام مكتملة."},
    "tasks_none_cleared": {"en": "No completed tasks to clear.", "fr": "Aucune tâche terminée à supprimer.", "ar": "لا توجد مهام مكتملة لحذفها."},
    "approval_share": {"en": "⚠️ Sharing “{topic}” to the shared knowledge base needs your confirmation. Reply “confirm” or “cancel”.",
                       "fr": "⚠️ Le partage de « {topic} » vers la base de connaissances partagée demande votre confirmation. Répondez « confirmer » ou « annuler ».",
                       "ar": "⚠️ مشاركة «{topic}» في قاعدة المعرفة المشتركة تتطلب تأكيدك. أجب بـ«تأكيد» أو «إلغاء»."},
    "approval_clear": {"en": "⚠️ This will delete your completed tasks. Reply “confirm” or “cancel”.",
                       "fr": "⚠️ Cette action supprimera vos tâches terminées. Répondez « confirmer » ou « annuler ».",
                       "ar": "⚠️ سيؤدي هذا إلى حذف مهامك المكتملة. أجب بـ«تأكيد» أو «إلغاء»."},
    "approval_generic": {"en": "⚠️ “{tool}” needs your confirmation. Reply “confirm” or “cancel”.",
                         "fr": "⚠️ « {tool} » demande votre confirmation. Répondez « confirmer » ou « annuler ».",
                         "ar": "⚠️ «{tool}» يتطلب تأكيدك. أجب بـ«تأكيد» أو «إلغاء»."},
    "approval_cancelled": {"en": "Cancelled — nothing was changed.", "fr": "Annulé — rien n’a été modifié.", "ar": "أُلغي — لم يتغير شيء."},
    "choose_open": {
        "en": "I found {count} of them. Which one should I open? Reply with its number (1, 2, …), say “all” to open every one, or “cancel”.\n{list}",
        "fr": "J’en ai trouvé {count}. Lequel veux-tu que j’ouvre ? Réponds avec son numéro (1, 2, …), « tous » pour tout ouvrir, ou « annule » pour ne rien faire.\n{list}",
        "ar": "وجدت {count}. أيّها تريد أن أفتح؟ أجب برقمه (1، 2، …)، أو «الكل» لفتحها كلها، أو «إلغاء» لعدم فعل شيء.\n{list}",
    },
    "no_pending_choice": {
        "en": "There is nothing to choose right now. Ask me to open a file first, and I will list the options if there are several.",
        "fr": "Il n’y a rien à choisir pour le moment. Demande-moi d’ouvrir un fichier, et je te proposerai la liste s’il y en a plusieurs.",
        "ar": "لا يوجد شيء للاختيار الآن. اطلب مني فتح ملفاً أولاً، وسأعرض القائمة إن وجدت عدة ملفات.",
    },
    "open_cancelled": {"en": "Okay, cancelled.", "fr": "D’accord, j’annule.", "ar": "حسناً، تم الإلغاء."},
    "opened_all": {"en": "I opened {count} of them.", "fr": "J’en ai ouvert {count}.", "ar": "فتحت {count}."},
    "open_failed": {
        "en": "I could not open {target} on this computer. Check that it exists or is installed, then try again.",
        "fr": "Je n’ai pas pu ouvrir {target} sur cet ordinateur. Vérifie que le fichier existe ou que l’application est installée, puis réessaie.",
        "ar": "لم أتمكن من فتح {target} على هذا الحاسوب. تحقق من وجوده أو من تثبيته ثم أعد المحاولة.",
        "es": "No he podido abrir {target} en este equipo. Comprueba que existe o está instalado e inténtalo de nuevo.",
        "de": "Ich konnte {target} auf diesem Computer nicht öffnen. Prüfe, ob es existiert oder installiert ist, und versuche es erneut.",
        "it": "Non sono riuscita ad aprire {target} su questo computer. Verifica che esista o sia installato, poi riprova.",
        "pt": "Não consegui abrir {target} neste computador. Verifique se existe ou está instalado e tente novamente.",
    },
    "model_offline": {"en": "I cannot reach the local AI model. Start Ollama with ollama serve, then try again.", "fr": "Je ne peux pas joindre le modèle IA local. Démarrez Ollama avec ollama serve, puis réessayez.", "ar": "لا أستطيع الاتصال بنموذج الذكاء الاصطناعي المحلي. شغّل Ollama بالأمر ollama serve ثم حاول مجدداً."},
    "chat_reset": {"en": "New conversation started. I have cleared this session's chat memory.", "fr": "Nouvelle conversation. J’ai effacé la mémoire de cette session.", "ar": "بدأت محادثة جديدة ومسحت ذاكرة هذه الجلسة."},
    "weather_city_missing": {"en": "Which city? For example: “weather in Nabeul”. You can set a default city with KIRA_CITY in .env.",
                             "fr": "Pour quelle ville ? Par exemple : « météo à Nabeul ». Vous pouvez définir une ville par défaut avec KIRA_CITY dans .env.",
                             "ar": "لأي مدينة؟ مثلاً: «الطقس في نابل». يمكنك تحديد مدينة افتراضية عبر KIRA_CITY في .env."},
    "weather_now": {"en": "Weather in {city}{country}: {condition}, {temp}°C (feels like {feels}°C), humidity {humidity}%, wind {wind} km/h. Today {tmin}–{tmax}°C, rain chance {rain}%.",
                    "fr": "Météo à {city}{country} : {condition}, {temp}°C (ressenti {feels}°C), humidité {humidity}%, vent {wind} km/h. Aujourd’hui {tmin}–{tmax}°C, risque de pluie {rain}%.",
                    "ar": "الطقس في {city}{country}: {condition}، {temp}°م (المحسوسة {feels}°م)، الرطوبة {humidity}%، الرياح {wind} كم/س. اليوم {tmin}–{tmax}°م، احتمال المطر {rain}%."},
    "holidays_upcoming": {"en": "Upcoming public holidays in {country} ({year}):\n{list}",
                          "fr": "Prochains jours fériés en {country} ({year}) :\n{list}",
                          "ar": "العطل الرسمية القادمة في {country} ({year}):\n{list}"},
    "holidays_none": {"en": "No public holidays left in {country} for {year}.",
                      "fr": "Plus aucun jour férié en {country} pour {year}.",
                      "ar": "لا توجد عطل رسمية متبقية في {country} لسنة {year}."},
    "currency_result": {"en": "{amount} {src} = {result} {dst} (rate {rate}, reference of {date}).",
                        "fr": "{amount} {src} = {result} {dst} (taux {rate}, référence du {date}).",
                        "ar": "{amount} {src} = {result} {dst} (السعر {rate}، مرجع {date})."},
    "wiki_not_found": {"en": "I found nothing on Wikipedia about “{topic}”.",
                       "fr": "Je n’ai rien trouvé sur Wikipédia à propos de « {topic} ».",
                       "ar": "لم أجد شيئاً في ويكيبيديا عن «{topic}»."},
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


# ─────────────────────────────────────────────
# Open choices: when several files/folders share a name, KIRA asks which
# one; the answer ("2", "deuxième", "tous", "annule") is handled here.
# ─────────────────────────────────────────────

_PENDING_OPEN = None
_PENDING_OPEN_TTL = 600.0

_CHOICE_WORDS = {
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10,
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "premier": 1, "premiere": 1, "1er": 1, "1ere": 1, "2e": 2, "3e": 3,
    "deuxieme": 2, "second": 2, "seconde": 2, "troisieme": 3,
    "quatrieme": 4, "cinquieme": 5, "sixieme": 6, "septieme": 7,
    "first": 1, "third": 3, "fourth": 4, "fifth": 5,
    "الأول": 1, "الثاني": 2, "الثالث": 3, "الرابع": 4, "الخامس": 5,
}
_CANCEL_WORDS = {"annule", "annuler", "cancel", "abandon", "laisse", "no", "non", "طغ", "الغاء", "إلغاء"}
_CHOICE_PREFIXES = ("le", "la", "les", "num", "numero", "n", "no", "the", "number", "رقم")
_ALL_WORDS = {"tous", "toutes", "tout", "all", "كل", "جميع"}


def set_pending_open(action, paths, name="", extra=None):
    global _PENDING_OPEN
    _PENDING_OPEN = {"action": action, "paths": list(paths), "name": name,
                     "extra": dict(extra or {}), "time": _time.monotonic()}


def _parsed_extra(parsed):
    """Parsing flags that must survive into the later choice/execution."""
    return {key: parsed[key] for key in ("any_kind",) if key in parsed}


def clear_pending_open():
    global _PENDING_OPEN
    _PENDING_OPEN = None


def pending_open():
    """A fresh pending choice, or None."""
    if _PENDING_OPEN and _time.monotonic() - _PENDING_OPEN["time"] < _PENDING_OPEN_TTL:
        return _PENDING_OPEN
    return None


def match_open_choice(text, count):
    """A pick (int), "all" or "cancel" from the user's answer, else None.

    Tolerates "le 2", "n°2", "numero 2", "the second", "all", "annule" ...
    """
    for raw_token in languages.fold(text).replace("°", "").replace("_", " ").split():
        token = raw_token.strip(".,!?;:»«()\"")
        if token in _CANCEL_WORDS:
            return "cancel"
        if token in _ALL_WORDS:
            return "all"
        for prefix in _CHOICE_PREFIXES:
            if token.startswith(prefix) and len(token) > len(prefix) and token[len(prefix):][:1].isdigit():
                token = token[len(prefix):].lstrip("°.:-_ ")
                break
        pick = _CHOICE_WORDS.get(token)
        if pick is None and token.isdigit():
            pick = int(token)
        if pick and 1 <= pick <= count:
            return pick
    return None


def is_pure_choice(text, count=10):
    """True only when the message is NOTHING BUT a choice answer ("2",
    "le 2", "la deuxième", "tous", "annule").

    Regression source: live test on 2026-09-27 where "raconte-moi une blague"
    was hijacked as a stray pick — 'une' maps to 1 — and answered with
    "Il n'y a rien à choisir". A French article inside a real sentence must
    never be mistaken for a pick."""
    tokens = [token.strip(".,!?;:»«()\"")
              for token in languages.fold(text).replace("°", "").replace("_", " ").split()]
    tokens = [token for token in tokens if token]
    if not tokens:
        return False
    for token in tokens:
        if token in _CANCEL_WORDS or token in _ALL_WORDS or token in _CHOICE_WORDS:
            continue
        if token.isdigit() or token in _CHOICE_PREFIXES:
            continue
        for prefix in _CHOICE_PREFIXES:
            if token.startswith(prefix) and len(token) > len(prefix) and token[len(prefix):][:1].isdigit():
                break
        else:
            return False
    return match_open_choice(text, count) is not None


def _shorten_path(path):
    home = str(Path.home()) if Path.home().exists() else ""
    return path.replace(home, "~", 1) if home and path.startswith(home) else path


def _open_all(backend, action, paths, language, metadata, extra=None):
    clear_pending_open()
    opened = 0
    extra = extra or {}
    for path in paths[:20]:
        try:
            result = backend.execute_action({**extra, "action": action, "target": path})
            if type(result) is int:
                opened += max(0, result)
            elif result:
                opened += 1
        except Exception:
            continue
    reply = message("opened_all", language, count=opened) or message("opened_all", "en", count=opened)
    return {"action": action, "success": opened > 0, "opened": opened, "response": reply, **metadata}


def process_command(backend, text, reply_language="auto", previous_language=None, interface_language="en", chat_only=False):
    text = str(text or "").strip()
    choice = languages.resolve_reply_language(text, reply_language, previous_language, interface_language)
    metadata = choice.metadata()
    learning_reply = try_web_learning(text)
    if learning_reply is not None:
        return {"action": "web_learn", "response": learning_reply, **metadata}
    if backend is None:
        return {"error": "Backend not available", "error_code": "backend_unavailable", **metadata}
    if not text:
        return {"action": "none", "response": "", **metadata}
    if choice.language_only:
        reply = message("auto" if choice.preference == "auto" else "language", choice.language)
        return {"action": "language", "response": reply or languages.LANGUAGES[choice.language]["native_name"] + " ✓", **metadata}
    if _PENDING_APPROVAL and not chat_only:
        pick = match_approval_choice(text)
        waiting = _PENDING_APPROVAL
        clear_pending_approval()  # One question, one answer; anything else expires it.
        if pick is not None:
            import kira_agents
            if pick == "cancel":
                kira_agents.resolve_approval(waiting["id"], approve=False, source="ui")
                drop_pending_plan(waiting["id"])  # a cancelled plan never resumes
                return {"action": waiting["action"], "success": False, "approval": "rejected",
                        "response": message("approval_cancelled", choice.language) or message("approval_cancelled", "en"),
                        **metadata}
            result = kira_agents.resolve_approval(waiting["id"], approve=True, source="ui")
            payload = _format_approved(waiting["action"], result, choice.language, metadata)
            # A confirmed plan approval continues the REMAINING steps.
            if pending_plan() and pending_plan().get("approval_id") == waiting["id"]:
                rest = resume_pending_plan()
                if rest is not None:
                    payload["response"] = (payload.get("response", "") + "\n" +
                                           str(rest.get("response", ""))).strip()
                    payload["plan"] = rest.get("plan", [])
                    payload["completed"] = rest.get("completed", [])
            return payload

    pending = pending_open()
    if pending and not chat_only and backend is not None:
        # Only a pure answer counts ("le 2", "tous"...): a real sentence that
        # merely contains 'une'/'deux' is a new request, not a pick.
        pick = match_open_choice(text, len(pending["paths"])) if is_pure_choice(text, len(pending["paths"])) else None
        if pick == "cancel":
            clear_pending_open()
            return {"action": "none", "response": message("open_cancelled", choice.language) or message("open_cancelled", "en"), **metadata}
        if pick == "all":
            return _open_all(backend, pending["action"], pending["paths"], choice.language, metadata,
                             extra=pending.get("extra", {}))
        if isinstance(pick, int):
            path = pending["paths"][pick - 1]
            action = pending["action"]
            clear_pending_open()
            success = bool(backend.execute_action({**pending.get("extra", {}), "action": action, "target": path}))
            if success and hasattr(backend, "build_reply"):
                reply = backend.build_reply(choice.language, action, Path(path).name)
            else:
                reply = message("open_failed", choice.language, target=Path(path).name) or message("action_failed", choice.language) or message("action_failed", "en")
            return {"action": action, "success": bool(success), "response": reply, **metadata}
        # Anything else is a new request; the old question expires.
        clear_pending_open()

    if pending is None and not chat_only:
        if is_pure_choice(text, 10) and len(text.split()) <= 3 and kira_open.parse_open_command(text) is None:
            return {"action": "none",
                    "response": message("no_pending_choice", choice.language) or message("no_pending_choice", "en"),
                    **metadata}

    try:
        canned = builtin_reply(text, choice.language)
        if canned:
            return {"action": "chat", "response": canned, **metadata}
        cleaned = backend.normalize_command(text)
        if not cleaned:
            return {"action": "none", "response": "", **metadata}
        special = None if chat_only else parse_special_command(cleaned)
        if special:
            return _direct_tool_route(special["action"], special, metadata, choice.language)
        parsed = None if chat_only else (parse_tool_command(cleaned) or backend.parse_simple_command(cleaned))
        if parsed and parsed.get("action", "none") != "none":
            action = parsed["action"]
            if action == "chat_reset":
                # 'clear chat' / 'efface la conversation': the voice loop
                # handled this, but the UI route fell into execute_action and
                # answered "I could not complete that action."
                try:
                    backend.reset_chat()
                except Exception:
                    return {"action": action, "success": False,
                            "response": message("action_failed", choice.language) or message("action_failed", "en"),
                            **metadata}
                return {"action": action, "success": True,
                        "response": message("chat_reset", choice.language) or message("chat_reset", "en"),
                        **metadata}
            if action in DIRECT_TOOL_ACTIONS:
                # Fast paths: tools return data immediately. The backend voice
                # handlers speak synchronously and would block this HTTP
                # response; the UI already displays the text and speaks it on
                # its own TTS path. No execute_action, no Ollama translation.
                # The standalone voice loop keeps its own speaking handlers.
                return _direct_tool_route(action, parsed, metadata, choice.language)
            matches = None
            if action in {"open_file", "open_folder"} and hasattr(backend, "resolve_open_matches"):
                try:
                    matches = backend.resolve_open_matches(parsed)
                except Exception:
                    matches = None
            if matches is not None and parsed.get("all"):
                result = backend.execute_action({**parsed, "candidates": matches})  # Search runs exactly once.
                success = bool(result)
                opened = result if type(result) is int else (1 if result else 0)
                reply = message("opened_all", choice.language, count=opened) or message("opened_all", "en", count=opened)
                return {"action": action, "success": opened > 0, "opened": opened, "response": reply, **metadata}
            if matches is not None and len(matches) > 1:
                set_pending_open(action, matches, name=str(parsed.get("target", "")),
                                 extra=_parsed_extra(parsed))
                listed = "\n".join(f"{index}. {_shorten_path(path)}" for index, path in enumerate(matches[:8], 1))
                reply = message("choose_open", choice.language, count=len(matches), list=listed) or message("choose_open", "en", count=len(matches), list=listed)
                return {"action": action, "needs_choice": True, "candidates": matches[:8], "response": reply, **metadata}
            if matches is not None and len(matches) == 1:
                # Open exactly the found path: no second scan, no ambiguity.
                success = bool(backend.execute_action({**parsed, "target": matches[0]}))
            elif matches is not None and len(matches) == 0:
                success = False  # Already searched everywhere; fail honestly.
            else:
                success = backend.execute_action(parsed)  # Exactly once, before any translation.
            if not success:
                reply = None
                if action in {"open_app", "open_url", "open_file", "open_folder"}:
                    target = str(parsed.get("target", "")).strip()
                    if target:
                        reply = message("open_failed", choice.language, target=target)
                reply = reply or message("action_failed", choice.language) or message("action_failed", "en")
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
        if not chat_only:
            # Programming requests first, BEFORE the planner: the tiny model
            # picks the right tool but invents arguments (live bug 2026-09-29:
            # "create a python project ui-demo" planned scaffold_project with
            # name="python"). The deterministic parser owns the phrasings it
            # knows; the planner only handles the rest.
            scaffold_args = parse_scaffold_request(cleaned)
            if scaffold_args:
                return _direct_tool_route("scaffold_project", scaffold_args,
                                          metadata, choice.language)
            # Multi-step requests first ("puis", "then", "ensuite"...):
            # an ordered 2-4 step plan runs sequentially; any consequential
            # step parks the WHOLE plan behind one approval card.
            try:
                import kira_planner
                steps = kira_planner.plan_steps(cleaned)
            except Exception:
                steps = None
            if steps:
                return _run_planned_steps(steps, metadata)
            # Optional planner (KIRA_PLANNER=1): the model picks ONE registered
            # tool or says none. Approval gates and validation stay intact;
            # any planner failure falls through to normal chat.
            try:
                import kira_planner
                plan = kira_planner.plan_command(cleaned)
            except Exception:
                plan = None
            if plan:
                plan_tool, plan_args = plan
                if plan_tool in DIRECT_TOOL_ACTIONS:
                    return _direct_tool_route(plan_tool, plan_args, metadata, choice.language)
                import kira_agents
                result = kira_agents.run(plan_tool, plan_args, source="planner")
                if result.ok:
                    return result.to_payload(**metadata)
                # A failed plan is not an error to the user: fall back to chat.
            else:
                # Programming requests need multi-file arguments (name,
                # template, code) that the tiny planner cannot synthesize
                # alone: derive the arguments deterministically instead of
                # falling through to chat.
                scaffold_args = parse_scaffold_request(cleaned)
                if scaffold_args:
                    return _direct_tool_route("scaffold_project", scaffold_args,
                                              metadata, choice.language)
        answer = call_with_options(backend.ask_chat, cleaned, language=choice.language)
        return {"action": "chat", "response": answer, **metadata}
    except languages.ReplyLanguageError:
        return {"error": message("wrong_language", interface_language) or message("wrong_language", "en"), "error_code": "reply_language_unavailable", **metadata}
    except Exception as error:
        return {"error": str(error), "error_code": "command_failed", **metadata}


# ── Approval flow: consequential tools confirm in the conversation ──────────

_PENDING_APPROVAL = None

_CONFIRM_WORDS = {"yes", "y", "confirm", "confirmed", "ok", "okay", "proceed", "go ahead", "do it",
                  "oui", "confirmer", "je confirme", "d'accord", "vas-y", "نعم", "تأكيد", "أكد"}
_CANCEL_WORDS = {"no", "n", "cancel", "stop", "abort", "non", "annule", "annuler", "لا", "إلغاء", "ألغ"}


def pending_approval():
    return _PENDING_APPROVAL


def clear_pending_approval():
    global _PENDING_APPROVAL
    _PENDING_APPROVAL = None


def _set_pending_approval(approval_id, action):
    global _PENDING_APPROVAL
    _PENDING_APPROVAL = {"id": approval_id, "action": action}


def _run_planned_steps(steps, metadata):
    """Execute a 2-4 step plan sequentially; one approval parks the rest.

    Read-only steps run immediately. At the FIRST consequential step, a single
    approval is parked for the remaining plan (_PENDING_PLAN); "confirm"
    resumes it, "cancel" drops it. Steps run through the registry exactly
    like single calls — activity, validation, structured failures.
    """
    import kira_agents
    results = []
    for index, step in enumerate(steps):
        result = kira_agents.run(step["tool"], step.get("args", {}), source="planner",
                                 approved=bool(step.get("__approved")))
        if result.ok:
            results.append({"tool": step["tool"], "ok": True,
                            "response": (result.response or "")[:200]})
            continue
        if result.error_code == "approval_required":
            approval_id = result.extra["approval_id"]
            _set_pending_approval(approval_id, step["tool"])
            global _PENDING_PLAN
            _PENDING_PLAN = {"approval_id": approval_id,
                             "steps": [{"__approved": True, **s} for s in steps[index:]],
                             "done": results}
            names = " → ".join(s["tool"] for s in steps[index:])
            text = (f"⚠️ The plan needs your confirmation for: {names}. "
                    f'Reply "confirm" or "cancel".'
                    if (metadata.get("language") or "en") == "en" else
                    f"⚠️ Le plan demande votre confirmation pour : {names}. "
                    f"Répondez « confirmer » ou « annuler ».")
            return {"action": "plan", "success": False, "needs_approval": True,
                    "approval_id": approval_id, "plan": [s["tool"] for s in steps],
                    "completed": results, "response": text, **metadata}
        results.append({"tool": step["tool"], "ok": False,
                        "error": (result.error or "")[:200]})
        break  # one failed step stops the plan (later steps may depend on it)
    ok_count = sum(1 for row in results if row["ok"])
    lines = "\n".join(f"{'✓' if row['ok'] else '✗'} {row['tool']}: "
                      f"{(row.get('response') or row.get('error') or '')[:120]}"
                      for row in results)
    return {"action": "plan", "success": ok_count == len(results) and bool(results),
            "plan": [s["tool"] for s in steps], "completed": results,
            "response": f"Plan ({ok_count}/{len(results)}) :\n{lines}", **metadata}


_PENDING_PLAN = None


def pending_plan():
    return _PENDING_PLAN


def clear_pending_plan():
    global _PENDING_PLAN
    _PENDING_PLAN = None


def drop_pending_plan(approval_id):
    """Forget a parked plan whose approval was cancelled/expired."""
    plan = pending_plan()
    if plan and plan.get("approval_id") == str(approval_id or ""):
        clear_pending_plan()
        return True
    return False


def resume_pending_plan():
    """Run the remaining steps after the approval was confirmed."""
    global _PENDING_PLAN
    plan = _PENDING_PLAN
    _PENDING_PLAN = None
    if not plan:
        return None
    return _run_planned_steps(plan["steps"], {})


def match_approval_choice(text):
    value = languages.fold(str(text or "")).strip(" .!!؟?,،;:«»\"'")
    if value in _CONFIRM_WORDS:
        return "confirm"
    if value in _CANCEL_WORDS:
        return "cancel"
    return None


def _format_approved(action, result, language, metadata):
    """Localize the data of an approved tool run, same shapes as the routes."""
    def msg(key, **values):
        return message(key, language, **values) or message(key, "en", **values) or ""
    if result.ok and action == "clear_completed_tasks":
        count = int(result.data or 0)
        if count <= 0:
            result.response = msg("tasks_none_cleared")
        else:
            result.response = msg("tasks_cleared_one" if count == 1 else "tasks_cleared", count=count)
        result.extra["cleared"] = count
    return result.to_payload(**metadata)


# ── Deterministic tool-command parsing (EN + FR) ────────────────────────────
# Route clear commands straight to tools without model calls. Tried BEFORE the
# backend parser, so phrasing tolerance here wins; anything unmatched falls
# through to the backend grammar and then to chat.

_TODO_PATTERNS = (
    re.compile(r"^(?:add|create|new)\s+(?:a\s+|another\s+)?(?:todo|to-?do|task|note)\s*[:\-]?\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(?:ajoute(?:r)?|cr[ée]e(?:r)?|nouvelle?)\s+(?:une\s+|un\s+)?(?:t[âa]che|todo|note)\s*[:\-]?\s+(.+)$", re.IGNORECASE),
)
_LIST_TASKS_PATTERNS = (
    re.compile(r"^(?:list|show|display|what\s+are)\s+(?:me\s+)?(?:my\s+|all\s+|the\s+)?(?:pending\s+)?(?:tasks?|todos?|to-?dos?)\??$", re.IGNORECASE),
    re.compile(r"^my\s+tasks?\??$", re.IGNORECASE),
    re.compile(r"^(?:liste|affiche|montre)(?:[- ]moi)?\s+(?:mes\s+|les\s+)?t[âa]ches(?:\s+en\s+attente)?\s*\??$", re.IGNORECASE),
    re.compile(r"^mes\s+t[âa]ches\s*\??$", re.IGNORECASE),
)
_WEATHER_PATTERNS = (
    re.compile(r"^(?:what(?:'s|\s+is)\s+(?:the\s+)?)?weather(?:\s+like)?(?:\s+(?:today|now|right\s+now))?(?:\s+in\s+(.+))?$", re.IGNORECASE),
    re.compile(r"^(?:quel\s+temps\s+fait[- ]il|(?:la\s+)?m[ée]t[ée]o)(?:\s+(?:aujourd'hui|maintenant))?(?:\s+(?:[àa]|en|sur)\s+(.+))?\s*$", re.IGNORECASE),
)
_HOLIDAYS_PATTERNS = (
    re.compile(r"^(?:what\s+are\s+the\s+|show\s+(?:me\s+)?|list\s+)?(?:next\s+|upcoming\s+)?(?:public\s+)?holidays(?:\s+in\s+([a-zà-ÿ'\- ]+?))?(?:\s+(?:in\s+|for\s+)?(\d{4}))?$", re.IGNORECASE),
    re.compile(r"^(?:quels?\s+sont\s+les\s+|liste\s+(?:les\s+)?|affiche\s+(?:les\s+)?)?(?:prochains?\s+)?jours?\s+f[ée]ri[ée]s(?:\s+(?:en|au|aux|[àa])\s+([a-zà-ÿ'\- ]+?))?(?:\s+(?:en\s+|pour\s+)?(\d{4}))?\s*$", re.IGNORECASE),
)
_WIKI_PATTERNS = (
    re.compile(r"^wiki(?:p[ée]dia)?\s*[:\-]?\s+(.+)$", re.IGNORECASE),
    re.compile(r"^who\s+(?:is|was)\s+(?!my\b|your\b|our\b)(.+)$", re.IGNORECASE),
    re.compile(r"^qui\s+(?:est|[ée]tait)\s+(?!mon\b|ma\b|mes\b|ton\b|ta\b|tes\b|notre\b|votre\b)(.+)$", re.IGNORECASE),
    re.compile(r"^من\s+(?:هو|هي)\s+(.+)$"),
)
_TRANSLATE_PATTERNS = (
    re.compile(r"^translate\s+(.+?)\s+(?:to|into)\s+([a-zA-Zà-ÿ]+)$", re.IGNORECASE),
    re.compile(r"^traduis(?:ez)?(?:[- ]moi)?\s+(.+?)\s+en\s+([a-zà-ÿ]+)$", re.IGNORECASE),
)
_CURRENCY_UNIT = r"[a-z]{3}|euros?|dollars?|dinars?|pounds?|livres?|dirhams?|yens?"
_CURRENCY_PATTERN = re.compile(
    r"^(?:convert\s+|convertis?\s+|change\s+|combien\s+font\s+)?"
    r"(\d+(?:[.,]\d+)?)\s*(" + _CURRENCY_UNIT + r")\s+(?:to|into|in|en|vers)\s+(" + _CURRENCY_UNIT + r")\s*$",
    re.IGNORECASE)
_CLEAR_TASKS_PATTERNS = (
    re.compile(r"^(?:clear|delete|remove)\s+(?:my\s+|the\s+|all\s+)?completed(?:\s+tasks?)?$", re.IGNORECASE),
    re.compile(r"^(?:supprime(?:r)?|efface(?:r)?|nettoie(?:r)?)\s+(?:mes\s+|les\s+)?t[âa]ches\s+termin[ée]es$", re.IGNORECASE),
)
_SHARE_PATTERNS = (
    # share knowledge <topic>: <content>  /  share knowledge: <topic>: <content>
    re.compile(r"^(?:share|publish|save|store)\s+(?:this\s+|the\s+)?(?:project\s+)?knowledge\s*[:\-]?\s+(.+?)\s*[:\-]\s+?(.+)$", re.IGNORECASE),
    re.compile(r"^(?:partage(?:r)?|publie(?:r)?|enregistre(?:r)?)\s+(?:la\s+|cette\s+)?connaissance\s*[:\-]?\s+(.+?)\s*[:\-]\s+?(.+)$", re.IGNORECASE),
)
_SEARCH_SHARED_PATTERNS = (
    re.compile(r"^(?:search|find|look\s?up|check|query|show)\s+(?:me\s+)?(?:in\s+|the\s+|our\s+)?shared\s+"
               r"(?:knowledge(?:\s+base)?|research|memory|notes)\s+(?:for|about|on|regarding)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(?:cherche(?:r)?|recherche(?:r)?|montre(?:[- ]moi)?)\s+(?:dans\s+)?(?:la\s+)?"
               r"(?:connaissance|m[ée]moire|recherche)s?\s+partag[ée]es?\s+(?:pour|sur|à propos de|concernant)?\s*(.+)$", re.IGNORECASE),
    re.compile(r"^(?:la\s+)?(?:recherche|connaissance|m[ée]moire)s?\s+partag[ée]es?\s*[:\-]?\s+"
               r"(?:pour|sur|à propos de|concernant)\s+(.+)$", re.IGNORECASE),
)

# Programming agent: "create a python project X" / "crée un projet web X".
# "new project X" alone stays planner-only to avoid false routes on mundane
# requests like "new project ideas".
_TPL = r"(?P<template>python|web|node|empty|vide)"
_PROJ = r"(?:programming\s+)?(?:projects?|projets?)"
_SCAFFOLD_PATTERNS = (
    # create a project X using python template / avec un template web
    re.compile(r"^(?:create|make|build|start|scaffold|cr[ée]e(?:r|z)?)\s+"
               r"(?:me\s+|moi\s+)?(?:a\s+|an\s+|the\s+|un\s+|une\s+|le\s+|la\s+)?"
               + _PROJ + r"\s*[:\-]?\s+(?P<name>.+?)\s+"
               r"(?:with|using|qui utilise|avec)\s+(?:a\s+|un\s+)?(?:template\s+)?"
               + _TPL + r"\s+template$", re.IGNORECASE),
    # create a python project X / build a node project X (template first, EN)
    re.compile(r"^(?:create|make|build|start|scaffold)\s+"
               r"(?:me\s+|a\s+|an\s+|the\s+)*"
               + _TPL + r"\s+" + _PROJ + r"\s*[:\-]?\s+(?P<name>.+)$", re.IGNORECASE),
    # crée un projet web X / génère un projet vide X (template after, FR)
    re.compile(r"^(?:cr[ée]e(?:r|z)?|g[ée]n[ée]re(?:r)?|construis)\s+"
               r"(?:moi\s+)?(?:un\s+|une\s+|le\s+|la\s+)?"
               + _PROJ + r"\s+" + _TPL + r"\s+(?:nomm[ée]\s+|appel[ée]\s+)?(?P<name>.+)$", re.IGNORECASE),
    # create a project X / scaffold project X / crée un projet X
    re.compile(r"^(?:create|make|build|start|scaffold|cr[ée]e(?:r|z)?|g[ée]n[ée]re(?:r)?|construis)\s+"
               r"(?:me\s+|moi\s+)?(?:a\s+|an\s+|the\s+|un\s+|une\s+|le\s+|la\s+)?"
               + _PROJ + r"\s*[:\-]?\s+(?P<name>.+)$", re.IGNORECASE),
)

_TEMPLATE_WORDS = {"python": "python", "web": "web", "node": "node", "empty": "empty",
                   "vide": "empty"}
_SCAFFOLD_NAME_BLOCKLIST = {"ideas", "idea", "name", "names", "template", "templates",
                            "plan", "plans", "management"}


def parse_tool_command(text):
    """Deterministic EN/FR grammar for the direct tool routes, or None."""
    value = str(text or "").strip().rstrip(".!?؟ ").strip()
    if not value:
        return None
    for pattern in _SEARCH_SHARED_PATTERNS:
        match = pattern.match(value)
        if match and match.group(1).strip():
            return {"action": "search_shared_knowledge", "query": match.group(1).strip()}
    for pattern in _SHARE_PATTERNS:
        match = pattern.match(value)
        if match and match.group(1).strip() and match.group(2).strip():
            return {"action": "share_project_knowledge", "kind": "project_knowledge",
                    "topic": match.group(1).strip(), "content": match.group(2).strip()}
    for pattern in _TODO_PATTERNS:
        match = pattern.match(value)
        if match and match.group(1).strip():
            return {"action": "add_todo", "title": match.group(1).strip()}
    for pattern in _LIST_TASKS_PATTERNS:
        if pattern.match(value):
            return {"action": "list_tasks"}
    for pattern in _CLEAR_TASKS_PATTERNS:
        if pattern.match(value):
            return {"action": "clear_completed_tasks"}
    for pattern in _WEATHER_PATTERNS:
        match = pattern.match(value)
        if match:
            return {"action": "get_weather", "city": (match.group(1) or "").strip()}
    for pattern in _HOLIDAYS_PATTERNS:
        match = pattern.match(value)
        if match:
            return {"action": "get_holidays", "country": (match.group(1) or "").strip(),
                    "year": (match.group(2) or "").strip()}
    match = _CURRENCY_PATTERN.match(value)
    if match:
        return {"action": "convert_currency", "amount": match.group(1).replace(",", "."),
                "from_currency": match.group(2), "to_currency": match.group(3)}
    for pattern in _TRANSLATE_PATTERNS:
        match = pattern.match(value)
        if match and match.group(1).strip():
            return {"action": "translate_text", "text": match.group(1).strip(),
                    "target_language": match.group(2).strip()}
    for pattern in _WIKI_PATTERNS:
        match = pattern.match(value)
        if match and match.group(1).strip():
            return {"action": "wiki_summary", "topic": match.group(1).strip()}
    return None


def parse_scaffold_request(text):
    """{'name', 'template'} for "create a python project X", else None.

    Kept out of parse_tool_command: "scaffold_project" runs with approval, so
    this only feeds the planner-fallback branch, never the fast path.
    """
    value = str(text or "").strip().rstrip(".!?؟ ").strip()
    for pattern in _SCAFFOLD_PATTERNS:
        match = pattern.match(value)
        if not match:
            continue
        name = str(match.group("name") or "").strip().strip("\"'")
        # Drop a trailing language tag: "create a project X in python".
        name = re.sub(r"\s+(?:in|en)\s+(?:python|web|node)$", "", name,
                      flags=re.IGNORECASE).strip()
        template = _TEMPLATE_WORDS.get(str(match.groupdict().get("template") or "").lower(), "")
        if not name or name.lower() in _SCAFFOLD_NAME_BLOCKLIST:
            continue
        if not re.match(r"^[^/:\\?*<>|\"]{1,64}$", name) or name in {".", ".."}:
            continue
        return {"name": name, "template": template}
    return None


# Actions answered directly from tools: data out, no backend speech, no model.
DIRECT_TOOL_ACTIONS = frozenset({
    "search_shared_knowledge", "share_project_knowledge",
    "add_reminder", "add_todo", "list_tasks", "clear_completed_tasks",
    "get_weather", "get_holidays", "convert_currency",
    "wiki_summary", "translate_text", "scaffold_project",
    "morning_briefing", "run_diagnostic", "code_build",
})


def _direct_tool_route(action, parsed, metadata, language):
    """Run one specialist tool via the registry; speech stays in the interface.

    Execution goes through kira_agents (validated arguments, activity feed,
    structured failures); this function only turns tool DATA into localized
    response text. The kira_voice_agent handlers for these actions speak every
    result synchronously, which is right for the microphone loop but blocks
    HTTP responses and double-speaks in the UI.
    """
    import kira_agents

    def msg(key, **values):
        return message(key, language, **values) or message(key, "en", **values) or ""

    if action == "search_shared_knowledge":
        result = kira_agents.run(action, {"query": str(parsed.get("query", "")).strip(), "limit": 3})
        return result.to_payload(**metadata)

    if action == "share_project_knowledge":
        topic = str(parsed.get("topic", "")).strip()
        result = kira_agents.run(action, {"topic": topic,
                                          "content": str(parsed.get("content", "")).strip()})
        if result.error_code == "approval_required":
            approval_id = result.extra["approval_id"]
            _set_pending_approval(approval_id, action)
            return {"action": action, "success": False, "needs_approval": True,
                    "approval_id": approval_id,
                    "response": msg("approval_share", topic=topic) or msg("approval_generic", tool=action),
                    **metadata}
        return result.to_payload(**metadata)

    if action in {"add_reminder", "add_todo"}:
        title = str(parsed.get("title", "")).strip()
        if not title:
            return {"action": action, "success": False, "response": msg("task_title_missing"),
                    "error": msg("task_title_missing"), "error_code": "task_title_missing", **metadata}
        args = {"title": title}
        if action == "add_reminder":
            args["due_at"] = str(parsed.get("due_at", "")).strip()
        result = kira_agents.run(action, args)
        if result.ok:
            result.response = msg("reminder_added" if action == "add_reminder" else "todo_added", title=title)
            result.extra["task_id"] = result.data
        return result.to_payload(**metadata)

    if action == "list_tasks":
        result = kira_agents.run(action, {})
        if result.ok:
            tasks = list(result.data or [])
            if not tasks:
                result.response = msg("tasks_none")
            else:
                listed = "\n".join(f"{index}. {str(task.get('title', '')).strip()}"
                                   for index, task in enumerate(tasks, 1))
                key = "tasks_pending_one" if len(tasks) == 1 else "tasks_pending"
                result.response = msg(key, count=len(tasks), list=listed)
            result.extra["tasks"] = [{"id": task.get("id"), "title": task.get("title"),
                                      "type": task.get("type"), "due_at": task.get("due_at")}
                                     for task in tasks]
        return result.to_payload(**metadata)

    if action == "clear_completed_tasks":
        result = kira_agents.run(action, {})
        if result.error_code == "approval_required":
            approval_id = result.extra["approval_id"]
            _set_pending_approval(approval_id, action)
            return {"action": action, "success": False, "needs_approval": True,
                    "approval_id": approval_id,
                    "response": msg("approval_clear") or msg("approval_generic", tool=action),
                    **metadata}
        if result.ok:
            count = int(result.data or 0)
            if count <= 0:
                result.response = msg("tasks_none_cleared")
            else:
                result.response = msg("tasks_cleared_one" if count == 1 else "tasks_cleared", count=count)
            result.extra["cleared"] = count
        return result.to_payload(**metadata)

    def _num(value):  # Missing readings show as "?" instead of "None".
        return "?" if value is None else value

    if action == "morning_briefing":
        started = _time.perf_counter()
        import kira_scheduler
        text, data = kira_scheduler.briefing(language)
        elapsed = int((_time.perf_counter() - started) * 1000)
        return {"action": action, "success": True, "response": text,
                "data": {"tasks": data.get("tasks", [])}, "elapsed_ms": elapsed,
                **metadata}

    if action == "run_diagnostic":
        started = _time.perf_counter()
        import kira_health
        report = kira_health.run_health_check()
        elapsed = int((_time.perf_counter() - started) * 1000)
        return {"action": action, "success": report["ok"],
                "response": report["response"], "checks": report["checks"],
                "elapsed_ms": elapsed, **metadata}

    if action == "code_build":
        started = _time.perf_counter()
        import kira_build
        result = kira_build.code_build(str(parsed.get("request", "")).strip(),
                                       str(parsed.get("project", "")).strip())
        elapsed = int((_time.perf_counter() - started) * 1000)
        return {"action": action, "success": bool(result.get("ok")),
                "response": result.get("response", "") or result.get("error", ""),
                "report": result, "elapsed_ms": elapsed, **metadata}

    if action == "scaffold_project":
        name = str(parsed.get("name", "")).strip()
        # Guard against planner-invented arguments (name="python" or empty):
        # never park an approval for a junk project name.
        if not name or name.lower() in _TEMPLATE_WORDS:
            text = ("Which project name should I use? For example: “create a python project todo-app”."
                    if language == "en" else
                    "Quel nom de projet dois-je utiliser ? Par exemple : « crée un projet python todo-app ».")
            return {"action": action, "success": False, "error_code": "invalid_name",
                    "response": text, **metadata}
        result = kira_agents.run(action, {"name": name,
                                          "template": str(parsed.get("template", "")).strip()})
        if result.error_code == "approval_required":
            approval_id = result.extra["approval_id"]
            _set_pending_approval(approval_id, action)
            text = ("⚠️ " + (f"Creating project '{name}' in the code workspace needs your confirmation. "
                             f"Reply \"confirm\" or \"cancel\"." if language == "en" else
                             f"La création du projet « {name} » dans l'espace de code demande votre confirmation. "
                             f"Répondez « confirmer » ou « annuler »."))
            return {"action": action, "success": False, "needs_approval": True,
                    "approval_id": approval_id, "response": text, **metadata}
        return result.to_payload(**metadata)

    if action == "get_weather":
        import kira_info
        city = str(parsed.get("city", "")).strip() or kira_info.default_city()
        if not city:
            text = msg("weather_city_missing")
            return {"action": action, "success": False, "response": text,
                    "error": text, "error_code": "city_missing", **metadata}
        result = kira_agents.run(action, {"city": city})
        if result.ok:
            data = result.data or {}
            lang = languages.normalize_language(language)
            condition = (data.get("condition") or {}).get(lang) or (data.get("condition") or {}).get("en", "")
            country = f" ({data['country']})" if data.get("country") else ""
            result.response = msg(
                "weather_now", city=data.get("city", city), country=country,
                condition=condition, temp=_num(data.get("temperature")),
                feels=_num(data.get("feels_like")), humidity=_num(data.get("humidity")),
                wind=_num(data.get("wind_kmh")), tmin=_num(data.get("today_min")),
                tmax=_num(data.get("today_max")), rain=_num(data.get("rain_chance_today")))
        return result.to_payload(**metadata)

    if action == "get_holidays":
        args = {"country": str(parsed.get("country", "")).strip()}
        year = str(parsed.get("year", "")).strip()
        if year.isdigit():
            args["year"] = int(year)
        result = kira_agents.run(action, args)
        if result.ok:
            data = result.data or {}
            upcoming = list(data.get("upcoming") or [])[:5]
            if upcoming:
                listed = "\n".join(f"- {row.get('date')} : {row.get('local_name') or row.get('name')}"
                                   for row in upcoming)
                result.response = msg("holidays_upcoming", country=data.get("country", ""),
                                      year=data.get("year", ""), list=listed)
            else:
                result.response = msg("holidays_none", country=data.get("country", ""),
                                      year=data.get("year", ""))
        return result.to_payload(**metadata)

    if action == "convert_currency":
        result = kira_agents.run(action, {"amount": str(parsed.get("amount", "")).strip(),
                                          "from_currency": str(parsed.get("from_currency", "")).strip(),
                                          "to_currency": str(parsed.get("to_currency", "")).strip()})
        if result.ok:
            data = result.data or {}
            result.response = msg("currency_result", amount=data.get("amount"),
                                  src=data.get("from"), dst=data.get("to"),
                                  result=data.get("result"), rate=data.get("rate"),
                                  date=data.get("date") or "?")
        return result.to_payload(**metadata)

    if action == "wiki_summary":
        topic = str(parsed.get("topic", "")).strip()
        result = kira_agents.run(action, {"topic": topic,
                                          "language": languages.normalize_language(language) or "en"})
        if result.ok:
            result.response = str((result.data or {}).get("summary", "")).strip()
        elif result.error_code == "tool_failed":
            text = msg("wiki_not_found", topic=topic)
            return {"action": action, "success": False, "response": text, "error": text,
                    "error_code": "wiki_not_found", **metadata}
        return result.to_payload(**metadata)

    if action == "translate_text":
        result = kira_agents.run(action, {"text": str(parsed.get("text", "")).strip(),
                                          "target_language": str(parsed.get("target_language", "")).strip(),
                                          "source_language": str(parsed.get("source_language", "")).strip()})
        if result.ok:
            result.response = str((result.data or {}).get("translated", "")).strip()
        return result.to_payload(**metadata)

    raise ValueError(f"Unrouted tool action: {action}")  # Defensive; DIRECT_TOOL_ACTIONS drives this.


_LEARN = re.compile(
    r"^(?:learn about|research|study|teach yourself(?: about)?)(?:\s+(.*))?$",
    re.IGNORECASE,
)

_BRIEFING_PATTERNS = (
    re.compile(r"^(?:briefing|point du matin|r[ée]sum[ée] du matin|morning briefing|good morning)\s*[!.?]*$", re.IGNORECASE),
)
_DIAGNOSTIC_PATTERNS = (
    re.compile(r"^(?:diagnostic|auto[- ]?diagnostic|self[- ]?test|health check|test de sant[ée])\s*[!.?]*$", re.IGNORECASE),
)
_BUILD_PATTERNS = (
    re.compile(r"^(?:code[- ])?build\s+(?:a\s+|an\s+|the\s+|un\s+|une\s+|le\s+|la\s+)?(.+?)(?:\s+(?:in|dans|dans le)\s+(?:project\s+|projet\s+)?(\S+))?\s*$", re.IGNORECASE),
    re.compile(r"^(?:g[ée]n[ée]re|d[ée]veloppe|impl[ée]mente|cr[ée]e le code)\s+(?:moi\s+)?(?:un\s+|une\s+)?(.+?)(?:\s+(?:dans|pour)\s+(?:le\s+)?(?:projet\s+)?(\S+))?\s*$", re.IGNORECASE),
)


def parse_special_command(text):
    """Deterministic route for briefing / diagnostic / code-build, or None.

    These are sentence-shaped commands the tiny planner mangles, so they get
    their own grammar like weather and tasks.
    """
    value = str(text or "").strip().rstrip(".!?؟ ").strip()
    for pattern in _BRIEFING_PATTERNS:
        if pattern.match(value):
            return {"action": "morning_briefing"}
    for pattern in _DIAGNOSTIC_PATTERNS:
        if pattern.match(value):
            return {"action": "run_diagnostic"}
    for pattern in _BUILD_PATTERNS:
        match = pattern.match(value)
        if match and (match.group(1) or "").strip():
            request = match.group(1).strip()
            project = (match.group(2) or "").strip()
            # 'build a todo app in python' is NOT 'project python' — keep the
            # project only when it names an existing workspace folder.
            if project:
                try:
                    import kira_code
                    folder = kira_code.workspace_root() / project
                    if not folder.is_dir():
                        project = ""
                except Exception:
                    project = ""
            return {"action": "code_build", "request": request, "project": project}
    return None


def try_web_learning(text):
    """Return a web-learning reply, or None for unrelated commands.

    Deliberately exclude 'remember' and 'memorize': private notes must not
    accidentally become web queries or shared research.
    """
    match = _LEARN.fullmatch(str(text or "").strip())
    if not match:
        return None
    topic = (match.group(1) or "").strip()
    if not topic:
        return "What would you like me to learn about?"
    try:
        # Through the registry: the research agent's activity feed shows the
        # run, arguments are validated, failures stay structured.
        import kira_agents
        result = kira_agents.run("web_learn", {"topic": topic}, source="ui")
        if result.ok:
            return result.response or str(result.data or "")
        return result.error or "I tried to learn about that but encountered an error."
    except Exception as exc:
        return f"I tried to learn about that but encountered an error: {exc}"
