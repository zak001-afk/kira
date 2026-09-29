"""Speech-only text sanitation; displayed replies are left unchanged."""

import re

# Match keycaps before their combining mark so ordinary numbers/#/* survive.
_EMOJI = re.compile(
    r"[0-9#*]\ufe0f?\u20e3|"
    r"[\U0001f000-\U0001faff\u2600-\u27bf"
    r"\u2300-\u23ff\u2b00-\u2bff\u2194-\u2199\u21a9-\u21aa"
    r"\u00a9\u00ae\u203c\u2049\u2122\u2139\u3030\u303d\u3297\u3299"
    r"\ufe0e\ufe0f\u200d\u20e3\U000e0020-\U000e007f]"
)


def clean_for_speech(text):
    """Remove emoji sequences and normalize whitespace without losing letters."""
    return re.sub(r"\s+", " ", _EMOJI.sub("", str(text or ""))).strip()
