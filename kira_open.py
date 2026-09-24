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
import time
import unicodedata
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

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


# Folders that must never be scanned when looking for a user file: they are
# huge and never contain the user's documents. Kept lowercase (already folded).
SKIP_DIR_NAMES = {
    "appdata", "application data", "local settings", "program files",
    "program files (x86)", "programdata", "windows", "library",
    "node_modules", "__pycache__", ".git", "venv", ".venv",
    "anaconda3", "miniconda3", "$recycle.bin", "system volume information",
    "cookies", "recent", "sendto", "start menu", "templates",
}


def find_file(name, search_dirs=None, max_entries=50000, time_budget=4.0):
    """Locate a file by name in the common folders. Returns a path or None.

    Scanning stops after time_budget seconds or max_entries files, and
    system/hidden folders are pruned, so a missing file fails fast instead
    of blocking KIRA for minutes.
    """
    deadline = time.monotonic() + max(0.5, time_budget)
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
            for root, subdirs, files in os.walk(folder):
                subdirs[:] = [d for d in subdirs if fold(d) not in SKIP_DIR_NAMES and not d.startswith(".")]
                depth = root[len(folder):].count(os.sep) + 1
                for entry in files:
                    scanned += 1
                    if scanned > max_entries or (scanned % 256 == 0 and time.monotonic() > deadline):
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


_START_MENU_CACHE = {"key": None, "time": 0.0, "walks": ()}
_START_MENU_CACHE_TTL = 60.0


def find_start_menu_app(name, dirs=None):
    """Best matching Start Menu shortcut (.lnk / .url) for an app name.

    The directory walk is cached for one minute: opening several things in a
    row must not re-scan the Start Menu every time.
    """
    wanted = fold(name)
    if not wanted:
        return None
    roots = list(dirs) if dirs is not None else start_menu_program_dirs()
    key = tuple(roots)
    now = time.monotonic()
    if _START_MENU_CACHE["key"] == key and now - _START_MENU_CACHE["time"] < _START_MENU_CACHE_TTL:
        walks = _START_MENU_CACHE["walks"]
    else:
        walks = []
        for base in roots:
            try:
                walks.extend(os.walk(base))
            except OSError:
                continue
        _START_MENU_CACHE.update(key=key, time=now, walks=walks)
    best = None
    best_score = 0
    for root, _subdirs, files in walks:
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


def windows_install_roots():
    """Common Windows install roots for a depth-limited .exe search."""
    roots = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if base:
            roots.append(base)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(os.path.join(local, "Programs"))
    seen, unique = set(), []
    for root in roots:
        if root not in seen:
            seen.add(root)
            unique.append(root)
    return unique


def find_installed_exe(name, bases=None):
    """A <name>.exe directly inside common install roots (depth <= 2)."""
    if bases is None and os.name != "nt":
        return None
    folded = fold(name)
    if not folded:
        return None
    candidates = {folded + ".exe", folded.replace(" ", "") + ".exe"}
    roots = list(bases) if bases is not None else windows_install_roots()
    for root in roots:
        try:
            entries = list(os.scandir(root))
        except OSError:
            continue
        for entry in entries:
            if entry.is_file() and entry.name.lower() in candidates:
                return entry.path
            if entry.is_dir():
                try:
                    children = list(os.scandir(entry.path))
                except OSError:
                    continue
                for child in children:
                    if child.is_file() and child.name.lower() in candidates:
                        return child.path
    return None


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
    install folders -> web version -> a browser page searching for the name.
    Never scans the user's documents: open requests must stay fast and must
    not open unrelated files.
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

    if os.name == "nt":
        installed = find_installed_exe(low)
        if installed:
            try:
                os.startfile(installed)
                return True
            except Exception:
                pass

    # Not installed: known web version, otherwise a browser page that
    # searches for the requested name.
    site = SITES.get(fold(low))
    if site and open_url(site):
        return True
    query = quote_plus(key)
    if query and open_url(f"https://www.google.com/search?q={query}"):
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
    "open", "open up", "launch", "start", "run",
    "ouvre", "ouvre-moi", "ouvrez", "ouvrir", "lance", "lance-moi", "lancer",
    "افتح", "افتح لي", "فتح", "شغل", "تشغيل",
)

FOLDER_PREFIX_WORDS = {"folder", "dossier", "مجلد"}

# Politeness and open wishes around the verb: "peux-tu m'ouvrir google",
# "je veux que tu ouvres facebook", "j'aimerais ouvrir X", "please open X",
# "i want you to open X", "من فضلك افتح X". Group 1 = verb, group 2 = target.
POLITE_OPEN = re.compile(
    r"^(?:est[- ]ce que (?:tu |vous )?)?"
    r"(?:peux[- ]tu|pourrais[- ]tu|pouvez[- ]vous|tu peux|vous pouvez|"
    r"je veux que (?:tu|vous)|je voudrais que (?:tu|vous)|j['’]aimerais que (?:tu|vous)|"
    r"j['’ ]?(?:aimerais|aime)|je voudrais|je veux|"
    r"can you|could you|would you|will you|i want (?:you )?to|i['’]?d like (?:you )?to|"
    r"s['’ ]?il (?:te|vous) pla[iî]t|stp|please|"
    r"ارجوك|أرجوك|من فضلك(?:م)?)"
    r"[,!?]?\s*(?:bien\s+|moi\s+|m(?:['’]\s*|\s+)|me\s+|nous\s+|لي\s+)?"
    r"(ouvrir|ouvres|ouvre|ouvrez|open|lancer|lances|lance|lancez|start|run|launch|شغل|شغّل|تشغيل|افتح|فتح)\s+(.+)$",
    re.IGNORECASE,
)

# Request words around the target ("ouvre moi ...", "pour moi", "please").
REQUEST_WORDS = {
    "moi", "me", "nous", "te", "vous", "il", "s", "stp", "please", "plait",
    "pour", "for", "لي", "من", "فضلك", "الرجاء",
}

# Container words naming WHAT is opened, not WHAT is opened
# ("l'application google" -> "google", "open the X app" -> "x").
APP_CONTAINER_WORDS = {
    "application", "aplication", "aplications", "applications", "app", "appli",
    "apps", "programme", "program", "programmes", "logiciel", "logiciels",
    "site", "sites", "page", "pages", "web", "exe",
    "تطبيق", "تطبيقات", "برنامج", "موقع", "صفحة",
}

_NOISE_WORDS = REQUEST_WORDS | LEADING_WORDS | APP_CONTAINER_WORDS


def _token_is_noise(token):
    """A token like "le'aplication" folds to several words; it is noise when
    every one of those words is filler."""
    parts = fold(token).split()
    return bool(parts) and all(part in _NOISE_WORDS for part in parts)


def clean_open_target(target):
    """Drop filler around the real target: 'moi le'aplication google' -> 'google'."""
    words = str(target or "").strip().split()
    for _ in range(6):
        changed = False
        while words and _token_is_noise(words[0]):
            words.pop(0)
            changed = True
        while words and _token_is_noise(words[-1]):
            words.pop()
            changed = True
        if not changed:
            break
    return " ".join(words).strip()


def parse_open_command(text):
    """Parse 'open X' / 'ouvre X' / 'شغل X' into an action dict, or None."""
    cleaned = str(text or "").strip()
    polite = POLITE_OPEN.match(cleaned)
    low = cleaned.lower()
    if polite:
        target = polite.group(2).strip()
    else:
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

    target = clean_open_target(target)
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
