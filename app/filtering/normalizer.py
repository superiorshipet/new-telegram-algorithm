import re
import unicodedata

_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_WHITESPACE = re.compile(r"\s+")
_TATWEEL = "\u0640"
_LETTER_TRANSLATION = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه",
    }
)


def normalize_arabic(value: str) -> str:
    """Normalize Arabic variants while preserving meaningful punctuation."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = _ARABIC_DIACRITICS.sub("", normalized)
    normalized = normalized.replace(_TATWEEL, "")
    normalized = normalized.translate(_LETTER_TRANSLATION)
    return _WHITESPACE.sub(" ", normalized).strip().casefold()
