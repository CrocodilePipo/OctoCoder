from __future__ import annotations

import re


_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_IMAGE_RE = re.compile(r"!\[([^]]*)]\([^)]+\)")
_LINK_RE = re.compile(r"\[([^]]+)]\([^)]+\)")
_RAW_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_HTML_RE = re.compile(r"<[^>]+>")
_SENTENCE_RE = re.compile(r".*?(?:[。！？!?]|\.(?=\s|$)|$)", re.DOTALL)


def extract_speakable_text(markdown: str) -> str:
    if not markdown.strip():
        return ""
    text = _FENCED_CODE_RE.sub(" ", markdown)
    text = _IMAGE_RE.sub(lambda match: match.group(1), text)
    text = _LINK_RE.sub(lambda match: match.group(1), text)
    text = _RAW_URL_RE.sub(" ", text)
    text = _HTML_RE.sub(" ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*(?:[-*+]\s+|\d+[.)]\s+|>\s*)", "", text)
    text = re.sub(r"[*_~]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
    return "\n".join(paragraphs)


def _hard_split(text: str, max_chars: int) -> list[str]:
    return [text[index:index + max_chars].strip() for index in range(0, len(text), max_chars)]


def split_speakable_text(text: str, max_chars: int = 3500) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    normalized = text.strip()
    if not normalized:
        return []

    units: list[str] = []
    for paragraph in normalized.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentences = [match.group(0).strip() for match in _SENTENCE_RE.finditer(paragraph)]
        units.extend(sentence for sentence in sentences if sentence)

    chunks: list[str] = []
    current = ""
    for unit in units:
        if len(unit) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(part for part in _hard_split(unit, max_chars) if part)
            continue
        candidate = f"{current} {unit}".strip() if current else unit
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = unit
    if current:
        chunks.append(current)
    return chunks
