import re
from typing import Iterable, List


_QUOTE_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00ab": '"',
        "\u00bb": '"',
    }
)

_DASH_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
    }
)

_INLINE_HYPHEN_RE = re.compile(r"([A-Za-z])-\s+([a-z])")


def normalize_unicode(text: str) -> str:
    cleaned = text.translate(_QUOTE_TRANSLATION).translate(_DASH_TRANSLATION)
    return cleaned.replace("\u00ad", "")


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_for_match(text: str) -> str:
    cleaned = normalize_unicode(text)
    cleaned = re.sub(r"-\s*\n\s*", "", cleaned)
    cleaned = cleaned.replace("\n", " ")
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return collapse_whitespace(cleaned)


def dehyphenate_lines(lines: List[str]) -> List[str]:
    output: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        while line.endswith("-") and i + 1 < len(lines):
            next_line = lines[i + 1].lstrip()
            if not next_line or not next_line[0].islower():
                break
            line = line[:-1] + next_line
            i += 1
        output.append(line)
        i += 1
    return output


def merge_inline_hyphenation(text: str) -> str:
    return _INLINE_HYPHEN_RE.sub(r"\1\2", text)


def canonical_line(line: str) -> str:
    cleaned = normalize_unicode(line)
    cleaned = cleaned.lower()
    cleaned = re.sub(r"\bpage\s+\d+\b", "page", cleaned)
    cleaned = re.sub(r"\d+", "#", cleaned)
    cleaned = collapse_whitespace(cleaned)
    return cleaned


def detect_repeated_lines(
    pages_lines: List[List[str]],
    *,
    top_n: int = 3,
    bottom_n: int = 3,
    threshold_ratio: float = 0.6,
) -> set[str]:
    counts: dict[str, int] = {}
    for lines in pages_lines:
        candidates = lines[:top_n] + lines[-bottom_n:]
        for line in candidates:
            key = canonical_line(line)
            if key:
                counts[key] = counts.get(key, 0) + 1
    threshold = max(2, int(len(pages_lines) * threshold_ratio))
    return {key for key, count in counts.items() if count >= threshold}


def remove_repeated_lines(lines: Iterable[str], repeated: set[str]) -> List[str]:
    output: List[str] = []
    for line in lines:
        if canonical_line(line) in repeated:
            continue
        if re.fullmatch(r"\s*\d+\s*", line):
            continue
        output.append(line)
    return output
