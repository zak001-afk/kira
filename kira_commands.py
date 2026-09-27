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
    pending = pending_open()
    if pending and not chat_only and backend is not None:
        pick = match_open_choice(text, len(pending["paths"]))
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
        stray = match_open_choice(text, 10)
        if stray is not None and len(text.split()) <= 3 and kira_open.parse_open_command(text) is None:
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
        parsed = None if chat_only else backend.parse_simple_command(cleaned)
        if parsed and parsed.get("action", "none") != "none":
            action = parsed["action"]
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
        answer = call_with_options(backend.ask_chat, cleaned, language=choice.language)
        return {"action": "chat", "response": answer, **metadata}
    except languages.ReplyLanguageError:
        return {"error": message("wrong_language", interface_language) or message("wrong_language", "en"), "error_code": "reply_language_unavailable", **metadata}
    except Exception as error:
        return {"error": str(error), "error_code": "command_failed", **metadata}


# Actions answered directly from tools: data out, no backend speech, no model.
DIRECT_TOOL_ACTIONS = frozenset({
    "search_shared_knowledge", "share_project_knowledge",
    "add_reminder", "add_todo", "list_tasks", "clear_completed_tasks",
})


def _direct_tool_route(action, parsed, metadata, language):
    """Run one tool and answer with its data; speech stays in the interface.

    The kira_voice_agent handlers for these actions speak every result
    synchronously, which is right for the microphone loop but blocks HTTP
    responses and double-speaks in the UI. Failures become structured error
    payloads instead of an HTTP 500 or a stuck request. Imports are lazy so
    optional dependencies only load for the routes that need them.
    """
    import kira_tools

    def msg(key, **values):
        return message(key, language, **values) or message(key, "en", **values) or ""

    if action == "search_shared_knowledge":
        query = str(parsed.get("query", "")).strip()

        def lookup():
            import kira_web  # Lazy: requests/bs4 stay optional for other routes.
            return kira_web.search_shared_knowledge(query, limit=3)

        return kira_tools.run_tool(action, lookup).to_payload(**metadata)

    if action == "share_project_knowledge":
        topic = str(parsed.get("topic", "")).strip()
        content = str(parsed.get("content", "")).strip()

        def share():
            import kira_web
            return kira_web.share_project_knowledge(topic, content)

        return kira_tools.run_tool(action, share).to_payload(**metadata)

    if action in {"add_reminder", "add_todo"}:
        title = str(parsed.get("title", "")).strip()
        due_at = str(parsed.get("due_at", "")).strip()
        if not title:
            return {"action": action, "success": False, "response": msg("task_title_missing"),
                    "error": msg("task_title_missing"), "error_code": "task_title_missing", **metadata}

        def add():
            import kira_tasks
            return kira_tasks.add_task(title=title,
                                       task_type="reminder" if action == "add_reminder" else "todo",
                                       due_at=due_at)

        result = kira_tools.run_tool(action, add)
        if result.ok:
            result.response = msg("reminder_added" if action == "add_reminder" else "todo_added", title=title)
            result.extra["task_id"] = result.data
        return result.to_payload(**metadata)

    if action == "list_tasks":
        def pending():
            import kira_tasks
            return kira_tasks.list_tasks(completed=False, limit=10)

        result = kira_tools.run_tool(action, pending)
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
        def clear():
            import kira_tasks
            return kira_tasks.clear_completed()

        result = kira_tools.run_tool(action, clear)
        if result.ok:
            count = int(result.data or 0)
            if count <= 0:
                result.response = msg("tasks_none_cleared")
            else:
                result.response = msg("tasks_cleared_one" if count == 1 else "tasks_cleared", count=count)
            result.extra["cleared"] = count
        return result.to_payload(**metadata)

    raise ValueError(f"Unrouted tool action: {action}")  # Defensive; DIRECT_TOOL_ACTIONS drives this.


_LEARN = re.compile(
    r"^(?:learn about|research|study|teach yourself(?: about)?)(?:\s+(.*))?$",
    re.IGNORECASE,
)


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
        import kira_web
        return kira_web.search_and_learn(topic)
    except Exception as exc:
        return f"I tried to learn about that but encountered an error: {exc}"
