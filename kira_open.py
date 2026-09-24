"""KIRA open-resolver: files, applications and web pages.

One place where KIRA decides what "open X" / "ouvre X" / "افتح X" means and
how to open it:

* web pages and Google services ("google", "gmail", "google maps", "youtube", ...)
* installed applications (built-in aliases + Windows Start Menu shortcut search)
* local files (absolute/relative path, or searched in the common folders)

Only the Python standard library is used so this module can be imported on
any platform (including CI), while the actual opening only happens on the
user's machine.
"""

import os
import re
import subprocess
import sys
import unicodedata
import webbrowser
from pathlib import Path

# ─────────────────────────────────────────────
# Text normalisation
# ─────────────────────────────────────────────

def fold(text):
    """Lowercase and strip accents/symbols for tolerant name matching."""
    text = unicodedata.normalize("NFD", str(text or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", text).strip()


# ─────────────────────────────────────────────
# Web pages / Google services
# ─────────────────────────────────────────────

SITES = {
    "google": "https://www.google.com",
    "google search": "https://www.google.com",
    "recherche google": "https://www.google.com",
    "google maps": "https://www.google.com/maps",
    "cartes": "https://www.google.com/maps",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "google docs": "https://docs.google.com/document/create",
    "docs": "https://docs.google.com/document/create",
    "google sheets": "https://sheets.google.com",
    "sheets": "https://sheets.google.com",
    "google slides": "https://slides.google.com",
    "slides": "https://slides.google.com",
    "google forms": "https://docs.google.com/forms",
    "google calendar": "https://calendar.google.com",
    "agenda google": "https://calendar.google.com",
    "google translate": "https://translate.google.com",
    "traducteur google": "https://translate.google.com",
    "traducteur": "https://translate.google.com",
    "google news": "https://news.google.com",
    "actualites google": "https://news.google.com",
    "google images": "https://www.google.com/imghp",
    "images google": "https://www.google.com/imghp",
    "google keep": "https://keep.google.com",
    "keep": "https://keep.google.com",
    "google meet": "https://meet.google.com",
    "meet": "https://meet.google.com",
    "gmail": "https://mail.google.com",
    "mail google": "https://mail.google.com",
    "youtube": "https://www.youtube.com",
    "youtube kids": "https://www.youtubekids.com",
    "wikipedia": "https://www.wikipedia.org",
    "github": "https://github.com",
    "gitlab": "https://gitlab.com",
    "stack overflow": "https://stackoverflow.com",
    "netflix": "https://www.netflix.com",
    "twitch": "https://www.twitch.tv",
    "reddit": "https://www.reddit.com",
    "amazon": "https://www.amazon.fr",
    "amazon france": "https://www.amazon.fr",
    "amazon com": "https://www.amazon.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "twitter": "https://x.com",
    "whatsapp": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org",
    "linkedin": "https://www.linkedin.com",
    "tiktok": "https://www.tiktok.com",
    "paypal": "https://www.paypal.com",
    # Web fallbacks for apps that may not be installed locally.
    "spotify": "https://open.spotify.com",
    "discord": "https://discord.com",
    "slack": "https://slack.com/signin",
    "steam": "https://store.steampowered.com",
    "teams": "https://teams.microsoft.com",
}


# ─────────────────────────────────────────────
# Applications (Windows first; keys are folded at lookup time)
# ─────────────────────────────────────────────

APPS = {
    # System
    "notepad": "notepad.exe",
    "bloc notes": "notepad.exe",
    "calculatrice": "calc.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "explorateur": "explorer.exe",
    "explorateur de fichiers": "explorer.exe",
    "maison": "explorer.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "powershell": "powershell.exe",
    "cmd": "cmd.exe",
    "invite de commandes": "cmd.exe",
    "command prompt": "cmd.exe",
    "task manager": "taskmgr.exe",
    "gestionnaire des taches": "taskmgr.exe",
    "control panel": "control.exe",
    "panneau de controle": "control.exe",
    "defender": "sdclt.exe",
    "windows defender": "sdclt.exe",
    "settings": "ms-settings:",
    "parametres": "ms-settings:",
    "store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:",
    "corbeille": "shell:RecycleBinFolder",
    "recycle bin": "shell:RecycleBinFolder",
    "camera": "microsoft.windows.camera:",
    "snipping tool": "SnippingTool.exe",
    "outils de capture": "SnippingTool.exe",
    "media player": "wmplayer.exe",
    "windows media player": "wmplayer.exe",
    "lecteur multimedia": "wmplayer.exe",
    "lecteur multimedia": "wmplayer.exe",
    # Microsoft Office / productivity
    "word": "winword.exe",
    "microsoft word": "winword.exe",
    "excel": "excel.exe",
    "microsoft excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "power point": "powerpnt.exe",
    "microsoft powerpoint": "powerpnt.exe",
    "onenote": "onenote.exe",
    "one note": "onenote.exe",
    "outlook": "outlook.exe",
    "microsoft outlook": "outlook.exe",
    "teams": "ms-teams:",
    # Browsers
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe",
    "mozilla firefox": "firefox.exe",
    "opera": "opera.exe",
    "brave": "brave.exe",
    "vivaldi": "vivaldi.exe",
    "arc": "Arc.exe",
    # Code / development
    "vscode": "code.exe",
    "vs code": "code.exe",
    "code": "code.exe",
    "visual studio code": "code.exe",
    "visual studio": "devenv.exe",
    "anaconda prompt": "anaconda_prompt.bat",
    # Communication / social
    "discord": "discord.exe",
    "slack": "slack.exe",
    "spotify": "spotify.exe",
    "vlc": "vlc.exe",
    "obs": "obs64.exe",
    "obs studio": "obs64.exe",
    "audacity": "audacity.exe",
    # Gaming / launchers
    "steam": "steam.exe",
    "epic games": "EpicGamesLauncher.exe",
    "epic": "EpicGamesLauncher.exe",
    "xbox": "XboxApp.exe",
    # Adobe / creative
    "photoshop": "Photoshop.exe",
    "adobe photoshop": "Photoshop.exe",
    "premiere": "Adobe Premiere Pro.exe",
    "premiere pro": "Adobe Premiere Pro.exe",
    "adobe premiere": "Adobe Premiere Pro.exe",
    "after effects": "After Effects.exe",
    "adobe after effects": "After Effects.exe",
    "illustrator": "Illustrator.exe",
    "lightroom": "Adobe Lightroom.exe",
    "gimp": "gimp-2.10.exe",
    "krita": "krita.exe",
    "blender": "blender.exe",
    # Arabic aliases (kept from the original command set)
    "مفكرة": "notepad.exe",
    "آلة حاسبة": "calc.exe",
    "حاسبة": "calc.exe",
    "متصفح": "chrome.exe",
    "كروم": "chrome.exe",
}


# ─────────────────────────────────────────────
# Well-known folders
# ─────────────────────────────────────────────

FOLDER_ALIASES = {
    "downloads": "~/Downloads",
    "telechargements": "~/Downloads",
    "documents": "~/Documents",
    "mes documents": "~/Documents",
    "desktop": "~/Desktop",
    "bureau": "~/Desktop",
    "pictures": "~/Pictures",
    "images": "~/Pictures",
    "photos": "~/Pictures",
    "music": "~/Music",
    "musique": "~/Music",
    "videos": "~/Videos",
    "home": "~",
    "maison": "~",
}


# ─────────────────────────────────────────────
# Files
# ─────────────────────────────────────────────

FILE_EXTENSIONS = {
    "pdf", "txt", "doc", "docx", "rtf", "odt", "xls", "xlsx", "csv", "ods",
    "ppt", "pptx", "odp", "md", "json", "xml", "html", "htm", "py", "js",
    "ts", "java", "c", "h", "cpp", "cs", "go", "rs", "php", "sql", "log",
    "zip", "rar", "7z", "tar", "gz", "jpg", "jpeg", "png", "gif", "webp",
    "bmp", "svg", "mp3", "wav", "ogg", "m4a", "flac", "mp4", "mkv", "avi",
    "mov", "webm", "eml", "msg", "apk", "psd", "ai", "indd", "sketch",
}

# Generic words that mark the target as a file ("ouvre le fichier rapport.pdf").
FILE_MARKER_WORDS = {"file", "fichier", "document", "doc", "lettre", "letter", "pdf", "ملف"}

# Leading articles / possessives dropped before a file or app name.
LEADING_WORDS = {
    "le", "la", "les", "l", "un", "une", "mon", "ma", "mes",
    "the", "my", "a", "an", "new", "nouveau", "nouvelle",
    "lapplication", "application", "app",
    "programme", "leprogramme", "برنامج", "تطبيق",
}


def strip_leading_words(text):
    """Drop leading articles / possessives ('mon rapport.pdf' -> 'rapport.pdf')."""
    words = str(text or "").strip().split()
    index = 0
    while index < len(words) and index < 3 and fold(words[index]) in LEADING_WORDS:
        index += 1
    rest = " ".join(words[index:]).strip()
    return rest if rest else str(text or "").strip()


def strip_file_markers(text):
    """Drop leading articles and file markers ('le fichier rapport' -> 'rapport')."""
    words = str(text or "").strip().split()
    index = 0
    while index < len(words) and index < 4:
        word = fold(words[index])
        if word in LEADING_WORDS or word in FILE_MARKER_WORDS:
            index += 1
            continue
        break
    rest = " ".join(words[index:]).strip()
    return rest if rest else str(text or "").strip()


def _last_segment(target):
    return str(target or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]


def _looks_like_path(target):
    target = str(target or "").strip()
    if not target:
        return False
    if "\\" in target or target.startswith("~"):
        return True
    if re.match(r"^[a-z]:[\\/]", target, re.IGNORECASE):
        return True
    if "/" in target and not target.startswith("http"):
        # "rapport/final" is path-like, but plain words with slashes are rare.
        return "." in _last_segment(target) or target.count("/") > 1
    return False


def _has_file_extension(target):
    segment = _last_segment(target)
    if "." not in segment:
        return False
    extension = segment.rsplit(".", 1)[1]
    return extension.lower() in FILE_EXTENSIONS


# ─────────────────────────────────────────────
# Resolution
# ─────────────────────────────────────────────

def resolve_open(target):
    """Classify an open request.

    Returns a dict {"kind": "url"|"app"|"folder"|"file", "target": str}
    or None when the target is empty.
    """
    raw = str(target or "").strip().rstrip(" .,!?؟;،:")
    if not raw:
        return None
    low = raw.lower()

    # 1. Explicit URL / domain (but "notes.txt" is a file, not a domain).
    if re.match(r"^(https?://|www\.)", low):
        return {"kind": "url", "target": low if low.startswith("http") else "https://" + low}
    last_label = low.rsplit(".", 1)[-1]
    if (
        re.fullmatch(r"[a-z0-9][a-z0-9-]*(\.[a-z0-9][a-z0-9-]*)+(:\d+)?(/.*)?", low)
        and len(last_label) >= 2
        and last_label not in FILE_EXTENSIONS
    ):
        return {"kind": "url", "target": "https://" + low}

    folded = fold(raw)
    if not folded:
        return None

    # 2. Known application (desktop first; the web fallback happens at execution).
    if folded in APPS:
        return {"kind": "app", "target": raw}

    # 3. Web page / Google service (exact name only, longest first).
    for name in sorted(SITES, key=len, reverse=True):
        if folded == fold(name):
            return {"kind": "url", "target": SITES[name]}

    # 4. Well-known folder.
    if folded in FOLDER_ALIASES:
        return {"kind": "folder", "target": raw}

    # 5. A path (C:\..., ~/..., relative with a directory part).
    if _looks_like_path(raw):
        return {"kind": "file", "target": raw}

    # 6. A filename with a known extension.
    if _has_file_extension(raw):
        return {"kind": "file", "target": strip_file_markers(raw)}

    # 7. Otherwise KIRA assumes an application.
    return {"kind": "app", "target": raw}


# ─────────────────────────────────────────────
# File search
# ─────────────────────────────────────────────

def common_file_dirs(base_home=None):
    """The folders KIRA searches when a file is requested by name."""
    home = Path(base_home).expanduser() if base_home else Path.home()
    pairs = (
        ("Desktop", "Bureau"),
        ("Documents", "Documents"),
        ("Downloads", "Téléchargements"),
        ("Pictures", "Images"),
        ("Music", "Musique"),
        ("Videos", "Vidéos"),
    )
    dirs = []
    for english, french in pairs:
        for candidate in (home / english, home / french):
            if candidate.is_dir():
                dirs.append(str(candidate))
                break
    dirs.append(str(home))
    return dirs


def find_file(name, search_dirs=None, max_entries=50000):
    """Locate a file by name in the common folders. Returns a path or None."""
    cleaned = strip_file_markers(name)
    if not cleaned:
        return None

    # Direct path?
    if cleaned.startswith(("/", "~")) or "\\" in cleaned or re.match(r"^[a-z]:", cleaned, re.IGNORECASE):
        path = Path(cleaned).expanduser()
        if path.exists():
            return str(path)
        if not path.is_absolute():
            for base in (Path.home(), Path.cwd()):
                candidate = (base / path).expanduser()
                if candidate.exists():
                    return str(candidate)
        return None

    wanted = fold(cleaned)
    if not wanted:
        return None
    wanted_stem = wanted.rsplit(".", 1)[0] if "." in wanted else wanted

    best = None
    best_score = 0
    scanned = 0
    for folder in (list(search_dirs) if search_dirs is not None else common_file_dirs()):
        try:
            for root, _subdirs, files in os.walk(folder):
                depth = root[len(folder):].count(os.sep) + 1
                for entry in files:
                    scanned += 1
                    if scanned > max_entries:
                        return best
                    label = fold(entry)
                    stem = label.rsplit(".", 1)[0] if "." in label else label
                    if label == wanted or stem == wanted:
                        return os.path.join(root, entry)
                    score = 0
                    if stem == wanted_stem and "." in wanted:
                        score = 90
                    elif stem.startswith(wanted) and len(wanted) >= 2:
                        score = 70 - depth
                    elif wanted in label and len(wanted) >= 4:
                        score = 50 - depth
                    if score > best_score:
                        best, best_score = os.path.join(root, entry), score
        except OSError:
            continue
    return best


# ─────────────────────────────────────────────
# Application / Start Menu search
# ─────────────────────────────────────────────

def start_menu_program_dirs():
    """Windows Start Menu program folders (user + machine)."""
    if os.name != "nt":
        return []
    dirs = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"))
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        dirs.append(os.path.join(programdata, "Microsoft", "Windows", "Start Menu", "Programs"))
    return [path for path in dirs if path and os.path.isdir(path)]


def find_start_menu_app(name, dirs=None):
    """Best matching Start Menu shortcut (.lnk / .url) for an app name."""
    wanted = fold(name)
    if not wanted:
        return None
    roots = list(dirs) if dirs is not None else start_menu_program_dirs()
    best = None
    best_score = 0
    for base in roots:
        try:
            walk = list(os.walk(base))
        except OSError:
            continue
        for root, _subdirs, files in walk:
            for entry in files:
                if not entry.lower().endswith((".lnk", ".url")):
                    continue
                label = fold(entry.rsplit(".", 1)[0])
                if not label:
                    continue
                if label == wanted:
                    return os.path.join(root, entry)
                score = 0
                if label.startswith(wanted) and len(wanted) >= 3:
                    score = 90 - len(label)
                elif wanted in label and len(wanted) >= 4:
                    score = 60 - len(label)
                elif label in wanted and len(label) >= 4:
                    score = 50 - len(label)
                if score > best_score:
                    best, best_score = os.path.join(root, entry), score
    return best


# ─────────────────────────────────────────────
# Opening
# ─────────────────────────────────────────────

def open_path(path):
    """Open a file or folder with the default application."""
    path = str(path or "").strip()
    if not path:
        return False
    try:
        if os.name == "nt":
            os.startfile(path)
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def open_url(url):
    """Open a web page in the default browser."""
    url = str(url or "").strip()
    if not url:
        return False
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False


def open_folder(target, base_home=None):
    """Open a folder by alias (téléchargements, bureau ...) or by path."""
    key = fold(target)
    folder = FOLDER_ALIASES.get(key, str(target or "").strip())
    if not folder:
        return False
    if base_home:
        folder = folder.replace("~", str(base_home))
    folder = os.path.expanduser(folder)
    return open_path(folder)


def open_file(target, base_home=None, search_dirs=None):
    """Open a local file: direct path first, then the common folders."""
    name = strip_file_markers(target)
    if not name:
        return False
    if name.startswith(("/", "~")) or "\\" in name or re.match(r"^[a-z]:", name, re.IGNORECASE):
        path = Path(name).expanduser()
        if base_home:
            path = Path(str(path).replace("~", str(base_home)))
        if path.exists():
            return open_path(path)
        return False
    if search_dirs is None and base_home:
        search_dirs = common_file_dirs(base_home)
    found = find_file(name, search_dirs=search_dirs)
    if found:
        return open_path(found)
    return False


def open_app(name, start_menu_dirs=None, base_home=None):
    """Open an installed application.

    Order: alias (folder/exe/URI) -> direct launch -> Start Menu shortcut ->
    same-named file -> web version if one is known.
    """
    key = str(name or "").strip()
    if not key:
        return False
    low = key.lower()
    value = APPS.get(fold(low), key)

    # Folder alias values ("maison", ...) and direct paths.
    if value and (os.path.isdir(value) or os.path.isfile(value)):
        return open_path(value)

    # URI schemes (ms-settings:, ms-teams:, mailto: ...) and shell: links.
    if re.fullmatch(r"[a-z][a-z0-9+.-]*:.*", value):
        if os.name == "nt":
            try:
                subprocess.Popen(value, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                pass
        # Non-Windows machines: use the web version when one exists.
        site = SITES.get(fold(low))
        return open_url(site) if site else False

    exe = value if value.lower().endswith((".exe", ".bat", ".cmd", ".lnk", ".url")) else f"{value}.exe"
    tried = set()
    for candidate in (exe, key):
        if not candidate or candidate in tried:
            continue
        tried.add(candidate)
        try:
            subprocess.Popen(candidate, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            continue

    shortcut = find_start_menu_app(low, dirs=start_menu_dirs)
    if shortcut:
        if os.name == "nt":
            try:
                os.startfile(shortcut)
                return True
            except Exception:
                pass
        if open_path(shortcut):
            return True

    if base_home:
        found = find_file(key, search_dirs=common_file_dirs(base_home))
    else:
        found = find_file(key)
    if found and open_path(found):
        return True

    site = SITES.get(fold(low))
    if site and open_url(site):
        return True
    return False


def open_target(resolved):
    """Execute a resolve_open() result. Returns True on success."""
    if not resolved:
        return False
    kind = resolved.get("kind")
    target = resolved.get("target", "")
    if kind == "url":
        return open_url(target)
    if kind == "folder":
        return open_folder(target)
    if kind == "file":
        return open_file(target)
    return open_app(target)


# ─────────────────────────────────────────────
# Command parsing
# ─────────────────────────────────────────────

OPEN_PREFIXES = (
    "open", "launch", "start", "run",
    "ouvre", "ouvrir", "lance", "lancer",
    "افتح", "فتح", "شغل", "تشغيل",
)

FOLDER_PREFIX_WORDS = {"folder", "dossier", "مجلد"}


def parse_open_command(text):
    """Parse 'open X' / 'ouvre X' / 'شغل X' into an action dict, or None."""
    cleaned = str(text or "").strip()
    low = cleaned.lower()
    target = None
    for prefix in OPEN_PREFIXES:
        p = prefix.lower()
        if low == p:
            return None
        if low.startswith(p + " "):
            target = cleaned[len(p):].strip()
            break
    if not target:
        return None

    target = strip_leading_words(target)
    if not target:
        return None

    # "open folder X" is an explicit folder request.
    words = target.split()
    if words and fold(words[0]) in FOLDER_PREFIX_WORDS:
        rest = " ".join(words[1:]).strip()
        if rest:
            return {"action": "open_folder", "target": rest}
        return None

    # "open X and search Y" is a combined command handled by the caller.
    if re.search(r"\s+and\s+search\s+", low) or re.search(r"\s+et\s+(?:cherche|recherche)\s+", low):
        return None

    # An explicit file word forces the file kind ("open file C:\...", "ouvre le document budget").
    force_file = False
    words = target.split()
    for index, word in enumerate(words):
        if fold(word) in FILE_MARKER_WORDS:
            force_file = True
            words = words[:index] + words[index + 1:]
            break
    if force_file:
        target = " ".join(words).strip() or target

    resolved = resolve_open(target)
    if not resolved:
        return None
    kind = resolved["kind"]
    if force_file and kind == "app":
        kind = "file"
    if kind == "url":
        return {"action": "open_url", "target": resolved["target"]}
    if kind == "folder":
        return {"action": "open_folder", "target": resolved["target"]}
    if kind == "file":
        return {"action": "open_file", "target": resolved["target"]}
    return {"action": "open_app", "target": resolved["target"]}
