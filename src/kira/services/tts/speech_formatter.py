"""Speech formatter — turns KIRA's written replies into natural spoken lines.

The layer sits between the persona and the TTS engine. It never invents
content: it strips what must not be read aloud (markdown, code, tables,
syntax), splits long sentences into short spoken ones, removes assistant
clichés ("Certainly, sir."), and caps the spoken length so KIRA stays concise
while the full answer remains visible in the UI.

Preserved on purpose: numbers, names, technical units (4.2 GB, 900 MB).
"""

from __future__ import annotations

import re
from typing import List, Optional

# ── Sentence splitting ────────────────────────────────────────────────────────

# Decimal numbers ("4.2"), common abbreviations ("Mr.", "e.g.") must not end
# a sentence. Everything else after . ! ? … ends one.
_NOT_SENTENCE_END = re.compile(
    r"(?:\d|[A-Za-z]\.|et al|e\.g|i\.e|vs|Mr|Mrs|Ms|Dr|St|Sr|Jr|Prof|Inc|Ltd|approx|fig|no|NB)"
    r"$",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"([.!?…]+[\"')\]]*\s+)")

# Clause joints where a long sentence may breathe. Comma/dash joints are
# always safe; bare conjunctions are tried too, but only where the head does
# not end on a dangling word ("...the reason is | because Chrome" would read
# badly, "...of RAM | while Discord..." reads naturally).
_COMMA_JOINTS = ("; ", " — ", " – ", ", but ", ", and ", ", so ", ", however, ")
_BARE_JOINTS = (" because ", " while ", " whereas ", " although ", " and ", " but ", " so ")
_DANGLING_HEAD = frozenset(
    "is are was were be been being am has have had do does did "
    "the a an of to for with on in at by from as that than which who whom "
    "and or but so because while whereas although though if when its their his her our your my"
    .split())
_LONG_SENTENCE_WORDS = 20

# Hedging that spoken dialogue does not need. Removed only at the start of a
# sentence, where dropping it cannot break grammar.
_HEDGES = (
    "based on the information available, ",
    "based on the information available ",
    "based on the available information, ",
    "based on the available information ",
    "based on my analysis, ",
    "based on my analysis ",
    "in my opinion, ",
    "it appears that ",
    "it seems that ",
    "it looks like ",
    "i believe that ",
    "i think that ",
    "i would say that ",
    "it is worth noting that ",
    "please note that ",
)

# Clichéd openers KIRA should never say aloud (removed entirely, with the rest
# of their sentence kept when one follows).
_CLICHE_OPENERS = (
    "certainly, sir. ",
    "of course, sir. ",
    "as you wish, sir. ",
    "right away, sir. ",
    "at your service, sir. ",
    "very good, sir. ",
    "certainly. ",
    "of course. ",
    "as you wish. ",
)

_VOCATIVE_SIR = re.compile(r"\b(?:yes|no|okay|ok|done|understood|right)\b[,.]?\s+(?:sir|madam)[,.]?\s*", re.IGNORECASE)
_SIR_WORD = re.compile(r"\b(sir|madam)\b[,.]?[ ]*", re.IGNORECASE)
_MARKUP_SPAN = re.compile(r"\s*([*_~]{1,3})(?=\S)(.+?)(?<=\S)\1\s*")
_LINK_SPAN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE0E\U0000FE0F\U0000200D\U000020E3"
    "]+"
)
_EXCLAMATION = re.compile(r"!+")
_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_DOT = re.compile(r"\.{4,}")


def _is_sentence_end(before: str) -> bool:
    """True when the characters right before a break really end a sentence."""
    tail = before.rstrip("\"')}]").rstrip()
    return not _NOT_SENTENCE_END.search(tail[-8:] if tail else "")


def split_sentences(text: str) -> List[str]:
    """Split text into spoken sentences.

    Newlines are hard breaks; punctuation splits the rest, except inside
    decimal numbers and abbreviations. Terminators are kept.
    """
    sentences: List[str] = []
    for block in re.split(r"\n+", str(text or "")):
        block = block.strip()
        if not block:
            continue
        start = 0
        for match in _SENTENCE_END.finditer(block):
            if not _is_sentence_end(block[max(0, match.start() - 8):match.start()]):
                continue
            piece = block[start:match.start() + 1].strip()
            if piece:
                sentences.append(piece)
            start = match.end()
        tail = block[start:].strip()
        if tail:
            sentences.append(tail)
    return sentences


def _strip_tables(markdown: str) -> str:
    lines = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.count("|") >= 2 or re.fullmatch(r":?-{3,}:?(\|:?-{3,}:?)+", stripped or ""):
            continue
        lines.append(line)
    return "\n".join(lines)


def _strip_markdown(markdown: str) -> str:
    """Remove everything that must not be read aloud, keep the words that may."""
    text = str(markdown or "")
    # Fenced code blocks: never read code aloud.
    text = re.sub(r"```[^\n]*\n[\s\S]*?```", " ", text)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Indented or inline code: keep content, drop the syntax.
    text = re.sub(r"``([^`]+)``", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Tables first (they carry structure, not dialogue).
    text = _strip_tables(text)
    # Links and images: the label, never the URL.
    text = _LINK_SPAN.sub(r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"https?://\S+", "link", text)
    # Headers, quotes, list markers, horizontal rules.
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}([-–—*+]|\d+[.)])\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}(:?-{3,}|={3,}|\*{3,})\s*$", " ", text, flags=re.MULTILINE)
    # Bold/italic/strikethrough spans.
    text = _MARKUP_SPAN.sub(r"\2", text)
    # Emoji and stray symbols.
    text = _EMOJI.sub(" ", text)
    return text


def _spoken_symbols(text: str) -> str:
    """Expand the few symbols that read naturally as words."""
    text = text.replace("°C", " degrees Celsius").replace("°F", " degrees Fahrenheit")
    text = text.replace("°", " degrees ")
    text = text.replace("&", " and ")
    text = text.replace("→", " to ").replace("=>", " gives ")
    text = re.sub(r"(\d)\s*%", r"\1 percent", text)
    text = text.replace("e.g., ", "for example, ").replace("e.g. ", "for example, ")
    text = text.replace("i.e., ", "that is, ").replace("i.e. ", "that is, ")
    text = text.replace("vs. ", "versus ").replace(" vs ", " versus ")
    return text


def _strip_cliches(text: str, keep_sir: bool) -> str:
    while True:
        lowered = " " + text.lower() + " "
        for cliche in _CLICHE_OPENERS:
            index = lowered.find(" " + cliche)
            if index >= 0:
                # ``lowered`` is text with one padding space, so the real cut
                # starts one character to the left of the padded index.
                start = max(0, index - 1)
                text = text[:start] + text[start + len(cliche):]
                break
        else:
            break
    if keep_sir:
        return text
    text = _VOCATIVE_SIR.sub("", text)
    text = _SIR_WORD.sub("", text)
    return text


def _split_long(sentence: str, max_words: int = _LONG_SENTENCE_WORDS) -> List[str]:
    """Break an over-long sentence at its most natural clause joints."""
    words = sentence.split()
    if len(words) <= max_words:
        return [sentence]
    lowered = sentence.lower()
    candidates = []
    floor = len(" ".join(words[:3]))
    for joint in _COMMA_JOINTS + _BARE_JOINTS:
        start = 0
        while True:
            index = lowered.find(joint, start)
            if index < 0:
                break
            if index > floor:
                candidates.append((index, joint))
            start = index + 1
    for index, joint in sorted(candidates):
        head = sentence[:index].strip().rstrip(",;:—–-")
        tail = sentence[index + len(joint):].strip()
        if not head or not tail:
            continue
        if head.split()[-1].lower().strip(",.!?;:\"'") in _DANGLING_HEAD:
            continue
        if len(head.split()) < 4 or len(tail.split()) < 5:
            continue
        return _split_long(head + ".", max_words) + _split_long(
            tail[0].upper() + tail[1:], max_words)
    return [sentence]


def _hedges_out(text: str) -> str:
    """Drop a hedge only at the very start of the sentence."""
    stripped = text.lstrip()
    lowered = stripped.lower()
    for hedge in _HEDGES:
        if lowered.startswith(hedge):
            rest = stripped[len(hedge):]
            if rest:
                return rest[0].upper() + rest[1:]
            return ""
    return text


def _dedupe(sentences: List[str]) -> List[str]:
    seen = set()
    result = []
    for sentence in sentences:
        key = re.sub(r"\W+", " ", sentence.lower()).strip()
        if key and key not in seen:
            seen.add(key)
            result.append(sentence)
    return result


def spoken_sentences(
    text: str,
    mode: str = "normal",
    max_sentences: Optional[int] = None,
    keep_sir: bool = False,
) -> List[str]:
    """Return the short, spoken-friendly sentences for ``text``."""
    limit = max_sentences
    cleaned = _strip_markdown(text)
    cleaned = _spoken_symbols(cleaned)
    cleaned = _strip_cliches(cleaned, keep_sir)

    pending: List[str] = []
    for raw in split_sentences(cleaned):
        raw = _EXCLAMATION.sub(".", raw)
        raw = _MULTI_DOT.sub("...", raw)
        raw = _MULTI_SPACE.sub(" ", raw).strip(" ,;")
        if raw and any(ch.isalnum() for ch in raw):
            pending.append(raw)

    # Work queue: every piece — original sentence or clause just split off —
    # gets hedge-stripping and splitting applied until it is short and clean.
    sentences: List[str] = []
    guard = 0
    while pending and guard <= 64:
        guard += 1
        raw = pending.pop(0)
        hedged = _hedges_out(raw)
        if hedged != raw:
            if hedged:
                pending.insert(0, hedged)
            continue
        pieces = _split_long(raw)
        if len(pieces) > 1:
            pending = pieces + pending
            continue
        sentences.append(raw)

    sentences = _dedupe(sentences)
    # Every spoken line should end on terminal punctuation: it is what the
    # phonemizer uses to breathe, and it keeps each clip sounding finished.
    sentences = [sentence if sentence.endswith((".", "!", "?", "…")) else sentence + "."
                 for sentence in sentences]
    if limit is None:
        from kira.services.tts.config import load_config
        limit = load_config().max_sentences
    if limit and len(sentences) > limit:
        sentences = sentences[:limit]
    return sentences


def format_speech(
    text: str,
    mode: str = "normal",
    max_sentences: Optional[int] = None,
    keep_sir: bool = False,
) -> str:
    """Format a written reply for speech: short sentences, natural pauses."""
    sentences = spoken_sentences(text, mode, max_sentences, keep_sir)
    return "\n\n".join(sentences)
