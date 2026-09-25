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
import shutil
import subprocess
import sys
import time
import unicodedata
import webbrowser
from pathlib import Path
from collections import deque
import difflib
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
    "yt": "https://www.youtube.com",
    "instagram": "https://www.instagram.com",
    "insta": "https://www.instagram.com",
    "insta gram": "https://www.instagram.com",
    "fb": "https://www.facebook.com",
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
# Default browser (Chrome unless the user asks for another one)
# ─────────────────────────────────────────────

BROWSER_ALIASES = {
    "chrome": "chrome", "google chrome": "chrome", "chromium": "chrome",
    "firefox": "firefox", "mozilla": "firefox", "mozilla firefox": "firefox",
    "edge": "edge", "microsoft edge": "edge", "ms edge": "edge", "msedge": "edge",
    "opera": "opera", "brave": "brave", "safari": "safari", "vivaldi": "vivaldi",
    "كروم": "chrome", "فايرفوكس": "firefox", "إيدج": "edge", "ادج": "edge",
}

DEFAULT_BROWSER = "chrome"


def set_default_browser(name):
    """Remember which browser KIRA should open pages with."""
    global DEFAULT_BROWSER
    key = BROWSER_ALIASES.get(fold(name), fold(name)) if name else ""
    DEFAULT_BROWSER = key or "chrome"


def default_browser():
    return DEFAULT_BROWSER


# A trailing browser name picks the browser for one request:
# "ouvre facebook sur firefox", "open maps in edge", "avec brave".
BROWSER_PATTERN = re.compile(
    r"\s+(?:sur|dans|avec|via|on|in|using|with|على)\s+"
    r"(google\s+chrome|chrome|chromium|firefox|mozilla(?:\s+firefox)?|"
    r"microsoft\s+edge|ms\s+edge|msedge|edge|opera|brave|safari|vivaldi|"
    r"كروم|فايرفوكس|إيدج|ادج)\s*[.!?؟]?\s*$",
    re.IGNORECASE,
)


def extract_browser(text):
    """Split a trailing browser name: -> (cleaned text, browser or None)."""
    cleaned = str(text or "").strip()
    match = BROWSER_PATTERN.search(cleaned)
    if not match:
        return cleaned, None
    browser = BROWSER_ALIASES.get(fold(match.group(1)))
    if not browser:
        return cleaned, None
    remaining = cleaned[: match.start()].rstrip(" ,.!؟،؛:")
    return (remaining, browser) if remaining else (cleaned, None)


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

WINDOWS_THIS_PC = "::{20D04FE0-3AEA-1069-A2D8-08002B30309D}"

FOLDER_ALIASES = {
    "ce pc": WINDOWS_THIS_PC,
    "cepc": WINDOWS_THIS_PC,
    "mon pc": WINDOWS_THIS_PC,
    "pc": WINDOWS_THIS_PC,
    "my pc": WINDOWS_THIS_PC,
    "this pc": WINDOWS_THIS_PC,
    "my computer": WINDOWS_THIS_PC,
    "computer": WINDOWS_THIS_PC,
    "ordinateur": WINDOWS_THIS_PC,
    "poste de travail": WINDOWS_THIS_PC,
    "poste": WINDOWS_THIS_PC,
    "جهازي": WINDOWS_THIS_PC,
    "هذا الكمبيوتر": WINDOWS_THIS_PC,
    "cepc windows": WINDOWS_THIS_PC,
    "corbeille": "shell:RecycleBinFolder",
    "recycle bin": "shell:RecycleBinFolder",
    "trash": "shell:RecycleBinFolder",
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

# Drive words ("disque c", "c:", "c drive", "disque dur" -> C:\).
DRIVE_REMOVE_WORDS = {
    "the", "le", "la", "les", "my", "mon", "ma",
    "disque", "lecteur", "drive", "disk", "partition", "local",
    "dur", "hard", "principal", "main", "system", "systeme",
    "قرص", "القرص", "محرك", "الصلب", "صلب", "السيب",
}
DRIVE_LETTER_WORDS = {"سي": "c", "دي": "d", "إي": "e", "اف": "f", "جي": "g", "اتش": "h"}


def parse_drive(text):
    """A drive letter from a phrase: 'disque c', 'c:', 'C drive', 'disque dur'."""
    low = fold(text)
    if not low:
        return None
    # Bare letter or letter with a colon: "c", "c:", "c:\".
    match = re.fullmatch(r"([a-z])\s*:?(?:\\+)?", low)
    if match:
        return match.group(1)
    words = [word for word in low.split()]
    letters = [word for word in words if len(word) == 1 and word.isalpha()]
    if letters:
        return letters[0]
    had_drive_word = any(word in DRIVE_REMOVE_WORDS for word in words) or low in DRIVE_REMOVE_WORDS
    words = [word for word in words if word not in DRIVE_REMOVE_WORDS]
    if not words:
        return "c" if had_drive_word else None
    if len(words) == 1:
        letter = DRIVE_LETTER_WORDS.get(words[0])
        if letter:
            return letter
        word = words[0]
        if re.fullmatch(r"[a-z]", word):
            return word
        if re.fullmatch(r"[a-z]:", word):
            return word[0]
    return None


FILE_EXTENSIONS = {
    "pdf", "txt", "doc", "docx", "rtf", "odt", "xls", "xlsx", "csv", "ods",
    "ppt", "pptx", "odp", "md", "json", "xml", "html", "htm", "py", "js",
    "ts", "java", "c", "h", "cpp", "cs", "go", "rs", "php", "sql", "log",
    "zip", "rar", "7z", "tar", "gz", "jpg", "jpeg", "png", "gif", "webp",
    "bmp", "svg", "mp3", "wav", "ogg", "m4a", "flac", "mp4", "mkv", "avi",
    "mov", "webm", "eml", "msg", "apk", "psd", "ai", "indd", "sketch",
}

# Generic words that mark the target as a file ("ouvre le fichier rapport.pdf").
FILE_MARKER_WORDS = {"file", "files", "fichier", "fichiers", "document", "documents", "doc", "docs", "lettre", "letter", "pdf", "ملف", "ملفات"}

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
# Approximate name matching ("insta"/"instagrame" -> instagram)
# ─────────────────────────────────────────────

def edit_distance(left, right, cap=4):
    """Levenshtein distance, giving up beyond cap."""
    if left == right:
        return 0
    if abs(len(left) - len(right)) > cap:
        return cap + 1
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i] + [0] * len(right)
        for j, right_char in enumerate(right, start=1):
            current[j] = min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (left_char != right_char),
            )
        previous = current
    return previous[-1]


def best_fuzzy_match(wanted, keys):
    """Best (key, score) among keys for a name with a typo or a nickname.

    "insta" matches "instagram" by prefix; "instagrame"/"facebok"/"yutube"
    match with a small edit distance. Very short names never match.
    """
    wanted = fold(wanted)
    if len(wanted) < 3:
        return None, 0
    best, best_score = None, 0
    for key in keys:
        label = fold(key)
        if not label or label == wanted:
            continue
        score = 0
        if label.startswith(wanted):
            score = 100 - len(label)
        elif wanted.startswith(label) and len(label) >= 3:
            score = 85 - len(label)
        else:
            limit = 1 if len(wanted) <= 5 else (2 if len(wanted) <= 9 else 3)
            distance = edit_distance(wanted, label, limit)
            if distance <= limit:
                score = 70 - distance * 12
        if score > best_score:
            best, best_score = key, score
    return best, best_score


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
    # 6bis. A drive: "le disque c", "c:", "c drive", "disque dur".
    if parse_drive(raw):
        return {"kind": "folder", "target": raw}

    # 7. A close name: "insta"/"instagrame" -> instagram, "facebok" -> facebook.
    if len(folded) >= 3:
        best_key, best_score, best_kind = None, 0, None
        for table, kind in ((APPS, "app"), (SITES, "url")):
            key, score = best_fuzzy_match(folded, list(table))
            if key and score > best_score:
                best_key, best_score, best_kind = key, score, kind
        if best_key and best_score >= 45:
            if best_kind == "url":
                return {"kind": "url", "target": SITES[best_key]}
            return {"kind": "app", "target": best_key}

    # 8. Otherwise KIRA assumes an application.
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
# Hard ceiling for one search operation (all drives included): the user
# waits at most this long before KIRA answers.
SEARCH_TIME_BUDGET = 5.0

SKIP_DIR_NAMES = {
    "appdata", "application data", "local settings", "program files",
    "program files (x86)", "programdata", "windows", "library",
    "node_modules", "__pycache__", ".git", "venv", ".venv",
    "anaconda3", "miniconda3", "$recycle.bin", "system volume information",
    "cookies", "recent", "sendto", "start menu", "templates",
}


def available_drives():
    """Every mounted drive root (C:\\, D:\\ ... on Windows, / elsewhere)."""
    if os.name == "nt":
        import string
        return [letter + ":\\" for letter in string.ascii_uppercase if os.path.exists(letter + ":\\")]
    return ["/"]


def deep_search_dirs():
    """All drive roots: searching here finds files anywhere on the PC."""
    drives = available_drives()
    home = str(Path.home())
    return drives + [home] if home not in drives else drives


def _walk_bfs(roots, prune_system):
    """Breadth-first walk of the given roots.

    Yields (directory, subdirs, files, depth). Shallow folders are scanned
    before deep ones, so a huge system tree (Program Files, WinSxS…) can no
    longer eat the whole budget before the other matches are reached.
    Symlinks and junctions are never followed, like os.walk's default.
    """
    queue = deque((root, 1) for root in roots)
    while queue:
        directory, depth = queue.popleft()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            yield directory, [], [], depth
            continue
        subdirs, files, children = [], [], []
        for entry in entries:
            name = entry.name
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if name.startswith(".") or (prune_system and fold(name) in SKIP_DIR_NAMES):
                    continue
                subdirs.append(name)
                children.append(os.path.join(directory, name))
            else:
                files.append(name)
        yield directory, subdirs, files, depth
        queue.extend((child, depth + 1) for child in children)


def find_file_matches(name, search_dirs=None, max_entries=50000, time_budget=4.0, limit=10, prune_system=True):
    """Every plausible file for a name: all exact matches first, then the
    scored approximations, best first. Used to ask the user which one."""
    deadline = time.monotonic() + max(0.5, time_budget)
    cleaned = strip_file_markers(name)
    if not cleaned:
        return []
    if cleaned.startswith(("/", "~")) or "\\" in cleaned or re.match(r"^[a-z]:", cleaned, re.IGNORECASE):
        path = Path(cleaned).expanduser()
        return [str(path)] if path.exists() else []

    wanted = fold(cleaned)
    if not wanted:
        return []
    wanted_stem = wanted.rsplit(".", 1)[0] if "." in wanted else wanted

    exact, scored = [], []
    scanned = 0
    for root, _subdirs, files, depth in _walk_bfs(
            list(search_dirs) if search_dirs is not None else common_file_dirs(), prune_system):
        for entry in files:
            scanned += 1
            if scanned > max_entries or (scanned % 256 == 0 and time.monotonic() > deadline):
                scored_paths = [path for _score, path in sorted(scored, key=lambda item: (-item[0], item[1]))]
                return (sorted(exact) + scored_paths)[:limit]
            label = fold(entry)
            stem = label.rsplit(".", 1)[0] if "." in label else label
            found = os.path.join(root, entry)
            if label == wanted or stem == wanted:
                exact.append(found)
                if len(exact) >= limit:
                    return sorted(exact)[:limit]
                continue
            score = 0
            if stem == wanted_stem and "." in wanted:
                score = 90
            elif stem.startswith(wanted) and len(wanted) >= 2:
                score = 70 - depth
            elif wanted in label and len(wanted) >= 3:
                score = 50 - depth
            if score == 0 and len(wanted) >= 3:
                ratio = difflib.SequenceMatcher(None, label, wanted).ratio()
                if ratio >= 0.75:  # typos: "delll", "delle", "dall"...
                    score = int(ratio * 60)
            if score > 0:
                scored.append((score, found))
    if exact or scored:
        scored_paths = [path for _score, path in sorted(scored, key=lambda item: (-item[0], item[1]))]
        return (sorted(exact) + scored_paths)[:limit]
    return [path for _score, path in sorted(scored, key=lambda item: (-item[0], item[1]))][:limit]


def find_file(name, search_dirs=None, max_entries=50000, time_budget=4.0):
    """Best file for a name (kept for compatibility: first exact match wins)."""
    matches = find_file_matches(name, search_dirs=search_dirs, max_entries=max_entries, time_budget=time_budget, limit=1)
    return matches[0] if matches else None


def find_folder_matches(name, search_dirs=None, max_entries=40000, time_budget=2.5, limit=10, prune_system=True):
    """Every plausible folder for a name: exact matches first, then scored."""
    deadline = time.monotonic() + max(0.5, time_budget)
    wanted = fold(strip_leading_words(name))
    if len(wanted) < 2:
        return []
    wanted_stem = wanted.rsplit(".", 1)[0]
    folders = list(search_dirs) if search_dirs is not None else common_file_dirs()
    exact, scored = [], []
    scanned = 0
    for directory, subdirs, _files, _depth in _walk_bfs(folders, prune_system):
        scanned += 1
        if scanned > max_entries or (scanned % 256 == 0 and time.monotonic() > deadline):
            scored_paths = [path for _score, path in sorted(scored, key=lambda item: (-item[0], item[1]))]
            return (sorted(exact) + scored_paths)[:limit]
        for entry in subdirs:
            label = fold(entry)
            found = os.path.join(directory, entry)
            if label == wanted or label == wanted_stem:
                exact.append(found)
                if len(exact) >= limit:
                    return sorted(exact)[:limit]
                continue
            score = 0
            if label.startswith(wanted) and len(wanted) >= 3:
                score = 80 - len(label)
            elif wanted.startswith(label) and len(label) >= 3:
                score = 65 - len(label)
            elif wanted in label and len(wanted) >= 3:
                score = 50 - len(label)
            if score == 0 and len(wanted) >= 3:
                ratio = difflib.SequenceMatcher(None, label, wanted).ratio()
                if ratio >= 0.75:  # typos: "delll", "delle", "dall"...
                    score = int(ratio * 60)
            if score > 0:
                scored.append((score, found))
    if exact or scored:
        scored_paths = [path for _score, path in sorted(scored, key=lambda item: (-item[0], item[1]))]
        return (sorted(exact) + scored_paths)[:limit]
    return [path for _score, path in sorted(scored, key=lambda item: (-item[0], item[1]))][:limit]


def find_folder(name, search_dirs=None, max_entries=40000, time_budget=2.5):
    """Best folder for a name (kept for compatibility: first exact wins)."""
    matches = find_folder_matches(name, search_dirs=search_dirs, max_entries=max_entries, time_budget=time_budget, limit=1)
    return matches[0] if matches else None


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
            else:
                limit = 1 if len(wanted) <= 5 else 2
                if edit_distance(wanted, label, limit) <= limit:
                    score = 45 - len(label)
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


def find_browser_exe(name, roots=None):
    """A browser executable on Windows (chrome, edge, firefox, brave, opera)."""
    key = BROWSER_ALIASES.get(fold(name), fold(name)) if name else ""
    if not key:
        return None
    if roots is None:
        if os.name != "nt":
            return None
        roots = windows_install_roots()
    relative = {
        "chrome": ["Google/Chrome/Application/chrome.exe"],
        "edge": ["Microsoft/Edge/Application/msedge.exe"],
        "firefox": ["Mozilla Firefox/firefox.exe"],
        "brave": ["BraveSoftware/Brave-Browser/Application/brave.exe"],
        "opera": ["Programs/Opera/launcher.exe"],
    }.get(key)
    if not relative:
        return None
    for root in roots:
        for path in relative:
            candidate = os.path.join(root, *path.split("/"))
            if os.path.isfile(candidate):
                return candidate
    return None


def find_installed_exe_deep(name, roots=None, time_budget=6.0):
    """A <name>.exe anywhere under the install folders (depth-budgeted walk)."""
    if roots is None:
        if os.name != "nt":
            return None
        roots = windows_install_roots()
    folded = fold(name)
    if not folded:
        return None
    candidates = {folded + ".exe", folded.replace(" ", "") + ".exe"}
    deadline = time.monotonic() + max(1.0, time_budget)
    scanned = 0
    for root in roots:
        try:
            for current, subdirs, files in os.walk(root):
                subdirs[:] = [d for d in subdirs if fold(d) not in SKIP_DIR_NAMES and not d.startswith(".")]
                scanned += 1
                if scanned % 256 == 0 and time.monotonic() > deadline:
                    return None
                for entry in files:
                    if entry.lower() in candidates:
                        return os.path.join(current, entry)
        except OSError:
            continue
    return None


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


def _browser_controller(name):
    """A webbrowser controller for a named browser, or None."""
    key = BROWSER_ALIASES.get(fold(name), fold(name)) if name else ""
    if not key or key in {"default", "system"}:
        return None
    try:
        return webbrowser.get(key)
    except webbrowser.Error:
        pass
    if os.name == "nt":
        path = find_browser_exe(key)
        if path:
            try:
                return webbrowser.BackgroundBrowser(path)
            except Exception:
                return None
    return None


def open_url(url, browser=None):
    """Open a web page with the requested browser, then KIRA's default
    (Chrome), then the system default as a last resort."""
    url = str(url or "").strip()
    if not url:
        return False
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    controller = _browser_controller(browser or DEFAULT_BROWSER)
    if controller is not None:
        try:
            controller.open(url)
            return True
        except Exception:
            pass
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False


def file_matches(name, parent=None, base_home=None, limit=10, deep_always=True,
                 time_budget=None):
    """Every matching file on the PC.

    Default: search the common folders first, then every drive, so the list
    is complete before deciding to open directly or to ask. A parent
    location limits the search exactly there.
    """
    name = strip_file_markers(name)
    if not name:
        return []
    if name.startswith(("/", "~")) or "\\" in name or re.match(r"^[a-z]:", name, re.IGNORECASE):
        path = Path(name).expanduser()
        if base_home:
            path = Path(str(path).replace("~", str(base_home)))
        return [str(path)] if path.exists() else []
    if parent:
        parent_dir = resolve_parent_dir(parent, base_home)
        if parent_dir:
            direct = os.path.join(parent_dir, name)
            if os.path.isfile(direct):
                return [direct]
            is_root = len(parent_dir) <= 3
            budget = 5.0 if is_root else 4.0
            if time_budget:
                budget = min(budget, time_budget)
            return find_file_matches(name, search_dirs=[parent_dir], limit=limit,
                                     prune_system=not is_root,
                                     max_entries=300000 if is_root else 150000,
                                     time_budget=budget)
        return []
    deadline = time.monotonic() + (time_budget if time_budget else SEARCH_TIME_BUDGET)
    matches = find_file_matches(name, search_dirs=common_file_dirs(base_home) if base_home else None,
                                limit=limit, time_budget=min(1.5, SEARCH_TIME_BUDGET))
    # Already ambiguous in the usual places: asking now is correct and fast.
    if len(matches) >= 2:
        return matches
    # Otherwise complete the search across every drive before deciding,
    # within the same overall deadline (max 5 s for the whole operation).
    if deep_always or not matches:
        for drive in deep_search_dirs():
            remaining = deadline - time.monotonic()
            if remaining < 0.3:
                break
            for path in find_file_matches(name, search_dirs=[drive], limit=limit,
                                          prune_system=False, max_entries=300000,
                                          time_budget=min(4.0, remaining)):
                if path not in matches:
                    matches.append(path)
            if len(matches) >= limit:
                break
    return matches[:limit]


def folder_matches(name, parent=None, base_home=None, limit=10, deep_always=True,
                   direct_only=True, time_budget=None):
    """Every matching folder on the PC (same policy as file_matches).

    direct_only: when the requested folder is a direct child of the named
    place, return it immediately. A full listing request ("cherche dell
    dans le c", "tous les dossiers qui contiennent…") passes False so the
    user sees every match, not just the first one."""
    if len(fold(strip_leading_words(name))) < 2:
        return []
    if parent:
        parent_dir = resolve_parent_dir(parent, base_home)
        if parent_dir:
            direct = os.path.join(parent_dir, strip_leading_words(name))
            if direct_only and os.path.isdir(direct):
                return [direct]
            is_root = len(parent_dir) <= 3
            budget = 5.0 if is_root else 4.0
            if time_budget:
                budget = min(budget, time_budget)
            return find_folder_matches(name, search_dirs=[parent_dir], limit=limit,
                                       prune_system=not is_root,
                                       max_entries=300000 if is_root else 150000,
                                       time_budget=budget)
        return []
    deadline = time.monotonic() + (time_budget if time_budget else SEARCH_TIME_BUDGET)
    matches = find_folder_matches(name, search_dirs=common_file_dirs(base_home) if base_home else None,
                                  limit=limit, time_budget=min(1.5, SEARCH_TIME_BUDGET))
    if len(matches) >= 2:
        return matches
    if deep_always or not matches:
        for drive in deep_search_dirs():
            remaining = deadline - time.monotonic()
            if remaining < 0.3:
                break
            for path in find_folder_matches(name, search_dirs=[drive], limit=limit,
                                            prune_system=False, max_entries=250000,
                                            time_budget=min(4.0, remaining)):
                if path not in matches:
                    matches.append(path)
            if len(matches) >= limit:
                break
    return matches[:limit]


def mixed_matches(name, parent=None, base_home=None, limit=20, deep_always=True):
    """Folders AND files whose name contains the words, for a bare search
    like "cherche dell dans le c": the user does not know (or care) which
    kind it is. Exact-name matches come first; both kinds stay visible."""
    folders = folder_matches(name, parent=parent, base_home=base_home,
                             limit=limit, deep_always=deep_always, direct_only=False,
                             time_budget=SEARCH_TIME_BUDGET / 2)
    files = file_matches(name, parent=parent, base_home=base_home,
                         limit=limit, deep_always=deep_always,
                         time_budget=SEARCH_TIME_BUDGET / 2)
    if not files:
        return folders[:limit]
    if not folders:
        return files[:limit]
    file_cap = max(1, limit // 2)
    return folders[:limit - file_cap] + files[:file_cap]


def open_folder(target, base_home=None, parent=None):
    """Open "Ce PC", a drive, a well-known folder, a path or a folder by name.

    With a parent location ("dans le dossier X", "sur le disque D"), the
    search starts inside it, which is both correct and fast.
    """
    raw = str(target or "").strip()
    key = fold(raw)
    folder = FOLDER_ALIASES.get(key, raw)
    if not folder:
        return False
    if base_home and folder.startswith("~"):
        folder = folder.replace("~", str(base_home))

    # Windows places: "Ce PC" (shell GUID) and shell: views.
    if os.name == "nt" and (folder.startswith("::") or folder.lower().startswith("shell:")):
        try:
            os.startfile(folder)
            return True
        except Exception:
            return False

    # Drives: "disque c", "c:", "disque dur" ...
    if not os.path.isdir(os.path.expanduser(folder)):
        letter = parse_drive(folder) or parse_drive(key)
        if letter and os.path.isdir(letter + ":\\"):
            folder = letter + ":\\"

    folder = os.path.expanduser(folder)
    if os.path.isdir(folder):
        return open_path(folder)

    # A parent location ("dans le dossier X", "sur le disque D") narrows it.
    if parent:
        parent_dir = resolve_parent_dir(parent, base_home)
        if parent_dir:
            direct = os.path.join(parent_dir, raw)
            if os.path.isdir(direct):
                return open_path(direct)
            found = find_folder(raw, search_dirs=[parent_dir], time_budget=8.0)
            if found:
                return open_path(found)

    # Otherwise search the PC for a folder with that name.
    search_dirs = common_file_dirs(base_home) if base_home else None
    found = find_folder(raw, search_dirs=search_dirs)
    if found:
        return open_path(found)
    # Deep search, drive by drive, so a busy C: never hides what is on D:.
    for drive in deep_search_dirs():
        found = find_folder(raw, search_dirs=[drive], max_entries=200000, time_budget=8.0)
        if found:
            return open_path(found)
    return False


def open_file(target, base_home=None, search_dirs=None, parent=None):
    """Open a local file: direct path, a parent location, the common folders,
    then every drive."""
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
    # A parent location ("dans le dossier X", "sur le disque D") narrows it.
    if parent:
        parent_dir = resolve_parent_dir(parent, base_home)
        if parent_dir:
            direct = os.path.join(parent_dir, name)
            if os.path.isfile(direct):
                return open_path(direct)
            found = find_file(name, search_dirs=[parent_dir], time_budget=8.0)
            if found:
                return open_path(found)

    if search_dirs is None:
        search_dirs = common_file_dirs(base_home) if base_home else None
    found = find_file(name, search_dirs=search_dirs)
    if found:
        return open_path(found)
    # Deep search, drive by drive, so a busy C: never hides what is on D:.
    for drive in deep_search_dirs():
        found = find_file(name, search_dirs=[drive], max_entries=250000, time_budget=10.0)
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

    # URI schemes (ms-settings:, ms-teams:, mailto:, shell: ...).
    if re.fullmatch(r"[a-z][a-z0-9+.-]*:.*", value):
        if os.name == "nt":
            try:
                os.startfile(value)
                return True
            except Exception:
                pass
        # Non-Windows machines: use the web version when one exists.
        site = SITES.get(fold(low))
        return open_url(site) if site else False

    exe = value if value.lower().endswith((".exe", ".bat", ".cmd", ".lnk", ".url")) else f"{value}.exe"

    # On PATH (CLI tools, apps registered by installers).
    for which_candidate in (low, key, value):
        if not which_candidate:
            continue
        located = shutil.which(which_candidate)
        if located:
            try:
                subprocess.Popen([located], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                try:
                    open_path(located)
                    return True
                except Exception:
                    pass

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
        # Portable apps without a shortcut: deeper time-limited walk.
        installed = find_installed_exe_deep(low)
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

FOLDER_PREFIX_WORDS = {"folder", "folders", "dossier", "dossiers",
                       "repertoire", "repertoires", "مجلد", "مجلدات"}

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


# "un dossier dans un dossier" / "sur le disque D" location phrases.
LOCATION_SPLIT = re.compile(
    r"\s+(?:dans|in)\s+(?:le\s+|la\s+|les\s+|l['’]\s*|the\s+)?"
    r"(?:dossier|répertoire|repertoire|folder|fichier|file)?\s*"
    r"|\s+sur\s+(?:le\s+|la\s+)?(?:disque|lecteur|drive|disk)\s+"
    r"|\s+on\s+(?:the\s+)?(?:drive|disk)\s+",
    re.IGNORECASE,
)

LOCATION_MARKER_WORDS = {
    "dossier", "folders", "folder", "repertoire", "répertoire", "fichier",
    "file", "disque", "lecteur", "drive", "disk", "the", "le", "la", "les",
    "l", "my", "mon", "ma", "الملف", "المجلد", "القرص",
}


def clean_location_words(text):
    """'le dossier documents' -> 'documents', 'le disque d' -> 'd'."""
    words = str(text or "").strip().split()
    while words and fold(words[0]) in LOCATION_MARKER_WORDS:
        words.pop(0)
    return " ".join(words).strip()


def split_location(text):
    """Split a nested request: 'projets dans le dossier documents' ->
    ('projets', 'documents'); 'missions sur le disque d' -> ('missions', 'd').

    A direct filename with an extension is never split.
    """
    cleaned = str(text or "").strip()
    if _has_file_extension(cleaned):
        return cleaned, None
    match = LOCATION_SPLIT.search(cleaned)
    if not match:
        return cleaned, None
    name = cleaned[: match.start()].strip().rstrip(" ,.!؟،؛:")
    parent = cleaned[match.end():].strip().rstrip(" ,.!؟،؛:")
    if not name or not parent:
        return cleaned, None
    parent = clean_location_words(parent)
    if not parent:
        return cleaned, None
    return name, parent


def resolve_parent_dir(parent, base_home=None):
    """Turn a location phrase into an existing start directory."""
    raw = str(parent or "").strip()
    if not raw:
        return None
    letter = parse_drive(raw)
    if letter:
        drive = letter + ":\\"
        if os.path.isdir(drive):
            return drive
        if os.path.isdir(letter + ":/"):
            return letter + ":/"
    key = fold(raw)
    if key in FOLDER_ALIASES:
        folder = FOLDER_ALIASES[key]
        if base_home:
            folder = folder.replace("~", str(base_home))
        folder = os.path.expanduser(folder)
        if os.path.isdir(folder):
            return folder
    candidate = Path(raw).expanduser()
    if base_home and not candidate.is_absolute():
        candidate = Path(base_home) / candidate
    if candidate.is_dir():
        return str(candidate)
    found = find_folder(raw, search_dirs=[base_home] if base_home else None)
    if found:
        return found
    # The named location itself may live anywhere ("dans le dossier missions").
    for drive in deep_search_dirs():
        found = find_folder(raw, search_dirs=[drive], max_entries=200000, time_budget=8.0)
        if found:
            return found
    return None


# "cherche les dossiers dell sur le c et ouvre chaque dossier..." is an
# open-all request: it must be executed, never sent to the chat model.
FIND_OPEN_PATTERN = re.compile(
    r"^\s*(?:cherche(?:z)?(?:\s+moi(?:\s+bien)?)?|trouve(?:z)?(?:\s+moi)?|"
    r"donnez?\s+moi|find|locate)\s+(.+?)\s*,?\s*"
    r"(?:et\s+|puis\s+|and\s+|then\s+)?(?:ouvre[sz]?|ouvrir|open|launch)\s+(.+)$",
    re.IGNORECASE,
)

DRIVE_PARENT_PATTERN = re.compile(
    r"\s+(?:sur|dans|on)\s+(?:le\s+|la\s+|the\s+)?(?:disque\s+|lecteur\s+|"
    r"drive\s+|disk\s+)?([a-z])\s*:?\s*\\*(?=\s|$|[.,!?؟])",
    re.IGNORECASE,
)

# "qui porte le nom de X" / "nommé X" / "named X" name the target.
NAMED_PHRASES = (
    "qui porte le nom de ", "qui porte le nom d'", "qui porte le nom ",
    "qui portent le nom de ", "qui portent le nom d'", "qui portent le nom ",
    "portant le nom de ", "portant le nom d'", "portant le nom ",
    "dont le nom est ", "nommé ", "nommée ", "nommés ", "nommées ",
    "appelé ", "appelée ", "appelés ", "appelées ",
    "qui contient le mot ", "qui contient les mots ", "qui contient le texte ",
    "qui contiennent le mot ", "contenant le mot ", "contenant les mots ",
    "contient le mot ", "contiennent le mot ", "contient le texte ",
    "qui contient ", "qui contiennent ", "contenant ", "contient ",
    "containing the word ", "that contains the word ", "with the word ",
    "containing ", "that contains ", "that contain ",
    "named ", "called ", "المسمى ", "التي تحمل اسم ", "الذي يحمل اسم ",
)

SEARCH_VERB_WORDS = {"porte", "portent", "portant", "nom", "named", "qui", "that", "les", "las", "the"}


def extract_drive_parent(text):
    """'les dossier dell sur le c' -> ('les dossier dell', 'c')."""
    cleaned = str(text or "").strip()
    match = DRIVE_PARENT_PATTERN.search(cleaned)
    if not match:
        return cleaned, None
    letter = match.group(1).lower()
    remaining = (cleaned[: match.start()] + " " + cleaned[match.end():]).strip()
    return remaining, letter


def strip_named_phrase(text):
    """Remove 'qui porte le nom de/d'', 'nommé', 'named' ... Returns the
    cleaned text; emptiness of the result tells the caller."""
    cleaned = str(text or "").strip()
    low = cleaned.lower()
    changed = False
    for phrase in NAMED_PHRASES:
        index = low.find(phrase)
        if index != -1:
            cleaned = (cleaned[:index] + " " + cleaned[index + len(phrase):]).strip()
            low = cleaned.lower()
            changed = True
    return cleaned, changed


def _meaningful_name(part):
    """The words left once fillers, folder/file nouns and name markers go."""
    noun_words = FOLDER_PREFIX_WORDS | {"dossiers", "folders", "fichiers", "files",
                                        "fichier", "file", "مجلدات", "ملفات"}
    words = []
    for word in str(part or "").split():
        token = fold(word)
        if not token or token in _NOISE_WORDS or token in noun_words or token in SEARCH_VERB_WORDS:
            continue
        if token in {"tous", "toutes", "tout", "toute", "all", "chaque", "chacun",
                     "chacune", "each", "every", "كل", "جميع"}:
            continue
        words.append(word)
    return " ".join(words).strip()


def collapse_find_open(text):
    """Turn a 'find ... and open ...' sentence into a plain open command."""
    match = FIND_OPEN_PATTERN.match(str(text or "").strip())
    if not match:
        return None
    search_part, search_parent = _find_scope(match.group(1).strip())
    open_part = _find_scope(match.group(2).strip())[0].strip()
    if _meaningful_name(open_part):
        replacement = f"ouvre {open_part}"
        if search_parent and not re.search(r"\b(?:dans|sur|in|on)\b", open_part, re.IGNORECASE):
            replacement += f" sur le disque {search_parent}"
        return replacement
    name = _meaningful_name(search_part)
    if not name:
        return None
    noun = next((word for word in search_part.split()
                 if fold(word) in {"dossier", "dossiers", "fichier", "fichiers",
                                   "folder", "folders", "file", "files",
                                   "مجلد", "مجلدات", "ملف", "ملفات"}), "")
    replacement = f"ouvre tous les {noun + ' ' if noun else ''}{name}"
    if search_parent:
        replacement += f" sur le disque {search_parent}"
    return replacement


FIND_VERB_PATTERN = re.compile(
    r"^\s*(?:(?:peux?[\s-]*tu|pourrais?[\s-]*tu|pourriez?[\s-]*vous|pouvez?[\s-]*vous|"
    r"s'il\s+(?:te|vous)\s+pla[îi]t,?)\s+)?"
    r"(?:cherche[sz]?(?:[\s-]+moi(?:[\s-]+bien)?)?|chercher|trouve[zs]?(?:[\s-]+moi)?|trouver|"
    r"rechercher|recherche[sz]?(?:[\s-]+moi(?:[\s-]+bien)?)?|"
    r"donnez?[\s-]+moi|find(?:[\s-]+me)?|locate|search(?:\s+for)?|"
    r"ابحث\s+عن|بحث\s+عن)\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)

_FIND_SCOPE_DRIVE = re.compile(
    r"\b(?:dans|sur|in|on|في)\s+(?:(?:tout|tous|toute|whole|entire|all|كل)\s+)?"
    r"(?:le\s+|la\s+|the\s+|my\s+|mon\s+|mes\s+)?"
    r"(?:(?:disque|lecteur|drive|disk|local(?:\s+disk)?|dur|قرص|القرص)\s+)?"
    r"\b([a-z])\b\s*:?\s*\\*\s*[.,!?؟]*$", re.IGNORECASE)

# Same scope phrase but at the START: "dans le c les dossiers dell".
_FIND_SCOPE_DRIVE_START = re.compile(
    r"^(?:dans|sur|in|on|في)\s+(?:(?:tout|tous|toute|whole|entire|all|كل)\s+)?"
    r"(?:le\s+|la\s+|the\s+|my\s+|mon\s+|mes\s+)?"
    r"(?:(?:disque|lecteur|drive|disk|local(?:\s+disk)?|dur|قرص|القرص)\s+)?"
    r"\b([a-z])\b\s*[:.]?\s*", re.IGNORECASE)

_FIND_SCOPE_PC = re.compile(
    r"\b(?:partout|(?:dans|sur|in|on|في)?\s*(?:tout|tous|toute|whole|entire|all)?\s*"
    r"(?:le\s+|la\s+|the\s+|my\s+|mon\s+|ma\s+|mes\s+)?"
    r"(?:pc|ordinateur|computer|machine|local))\s*[.!؟?]*$", re.IGNORECASE)

_FIND_PLURAL_MARKERS = {"tous", "toutes", "chaque", "chacun", "chacune", "every",
                        "each", "all", "les", "des", "كل", "جميع"}
_FIND_FOLDER_NOUNS = {"dossier", "dossiers", "folder", "folders",
                      "repertoire", "repertoires", "مجلد", "مجلدات"}
_FIND_FILE_NOUNS = {"fichier", "fichiers", "file", "files", "ملف", "ملفات"}


def _find_scope(text):
    """Split a search scope placed before OR after the target.

    parent is a drive letter ("dans tous le local c" -> "c"), "" for the
    whole PC ("tout le pc", "partout", "dans le local") or None. Both word
    orders are understood: "cherche dans le c les dossiers dell" and
    "cherche les dossiers dell dans le c".
    """
    cleaned = str(text or "").strip()
    start = _FIND_SCOPE_DRIVE_START.match(cleaned)
    if start:
        rest = cleaned[start.end():].strip()
        if rest:
            return rest, start.group(1).lower()
    drive = _FIND_SCOPE_DRIVE.search(cleaned)
    if drive:
        return cleaned[:drive.start()].strip(), drive.group(1).lower()
    pc = _FIND_SCOPE_PC.search(cleaned)
    if pc:
        return cleaned[:pc.start()].strip(), ""
    return cleaned, None


def parse_find_command(text):
    """Bare 'cherche/trouve (le) dossier/fichier X [dans le local c / le pc]'.

    A local search is an action, never a chat message: plural requests open
    every match, singular ones follow the standard flow (one match opens,
    several ask which one). Returns None for anything else (web search,
    questions), so those keep their current path.
    """
    cleaned = str(text or "").strip()
    low = cleaned.lower()
    if re.search(r"\b(?:internet|google|youtube|chrome|edge|firefox|en\s+ligne|online|web)\b", low):
        return None
    match = FIND_VERB_PATTERN.match(cleaned)
    if not match:
        return None
    rest, parent = _find_scope(match.group(1).strip())
    words = rest.split()
    kind, plural, noun_index = None, False, -1
    for index, word in enumerate(words):
        token = fold(word)
        if token.startswith("ال") and len(token) > 4:
            token = token[2:]
        if token in _FIND_FOLDER_NOUNS:
            kind = "folder"
        elif token in _FIND_FILE_NOUNS:
            kind = "file"
        else:
            continue
        plural = plural or token in {"dossiers", "folders", "repertoires", "مجلدات",
                                     "fichiers", "files", "ملفات"}
        noun_index = index
        break
    if any(fold(word) in _FIND_PLURAL_MARKERS for word in words[:noun_index if noun_index > 0 else 0]):
        plural = True
    body = " ".join(words[noun_index + 1:]) if noun_index >= 0 else rest
    named_part, had_named = strip_named_phrase(body)
    name = _meaningful_name(named_part)
    if not name and noun_index >= 0:
        # English order: "find the dell folder" (name before the noun).
        name = _meaningful_name(" ".join(words[:noun_index]))
        had_named = had_named or bool(name)
    if not name:
        return None
    if kind is None and not parent and not had_named:
        return None  # a generic search/question, not a local find
    action = {"action": "open_folder" if kind != "file" else "open_file", "target": name}
    if kind is None:
        # No noun said: search folders AND files ("cherche dell dans le c"),
        # the user does not know which kind it is.
        action["any_kind"] = True
    if parent:
        action["parent"] = parent
    if plural:
        action["all"] = True
    return action


def parse_open_command(text):
    """Parse 'open X' / 'ouvre X' / 'شغل X' into an action dict, or None."""
    cleaned = str(text or "").strip()
    collapsed = collapse_find_open(cleaned)
    if collapsed:
        cleaned = collapsed
    else:
        located = parse_find_command(cleaned)
        if located:
            return located
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

    # A trailing browser name ("sur firefox", "in edge") picks the browser.
    target, browser = extract_browser(target)
    if not target:
        return None

    # A nested location ("dans le dossier X", "sur le disque D") narrows it.
    target, parent = split_location(target)
    if not target:
        return None

    # "dossier qui porte le nom dell" -> "dell".
    target, had_named = strip_named_phrase(target)
    if not target:
        return None

    # "ouvre tous les rapports" / "open all reports": open every match.
    all_requested = had_named
    words = target.split()
    if words and fold(words[0]) in {"tous", "toutes", "tout", "toute", "all", "chaque",
                                    "chacun", "chacune", "each", "every", "كل", "جميع"}:
        rest = " ".join(words[1:]).strip()
        if not rest:
            return None  # "ouvre tous" alone is not a valid request
        all_requested = True
        target = strip_leading_words(rest)
        words = target.split()
        if not target:
            return None

    # "open folder X" is an explicit folder request.
    words = target.split()
    if words and fold(words[0]) in FOLDER_PREFIX_WORDS:
        rest = " ".join(words[1:]).strip()
        if rest or not all_requested:
            if rest:
                rest, _ = extract_browser(rest)
            rest, nested = split_location(rest) if rest else ("documents", None)
            if not rest:
                rest = "documents"  # a bare "open folder" opens Documents
            parent = parent or nested
            return {"action": "open_folder", "target": rest,
                    **({"parent": parent} if parent else {}),
                    **({"all": True} if all_requested else {})}
        # A bare "tous les dossiers" keeps "dossiers" as the searched name.

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
    if all_requested and kind == "app":
        folder_noun = bool(words) and fold(words[0]) in FOLDER_PREFIX_WORDS | {"dossiers", "folders", "مجلدات"}
        kind = "folder" if folder_noun else "file"
    if parent and kind == "app":
        kind = "folder"
    # "ouvre spotify sur firefox": an app requested inside a named browser
    # becomes its web version.
    if browser and kind == "app" and fold(resolved["target"]) in SITES:
        return {"action": "open_url", "target": SITES[fold(resolved["target"])], "browser": browser}
    if kind == "url":
        action = {"action": "open_url", "target": resolved["target"]}
    elif kind == "folder":
        action = {"action": "open_folder", "target": resolved["target"]}
    elif kind == "file":
        action = {"action": "open_file", "target": resolved["target"]}
    else:
        action = {"action": "open_app", "target": resolved["target"]}
    if browser and kind == "url":
        action["browser"] = browser
    if parent and kind in {"folder", "file"}:
        action["parent"] = parent
    if all_requested and kind in {"folder", "file"}:
        action["all"] = True
    return action
