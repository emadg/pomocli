"""Text helpers for normalizing user-facing names (projects, tasks)."""

import re

_STOPWORDS = frozenset({
    "a", "an", "the",
    "and", "or", "but", "nor",
    "for", "of", "in", "on", "at", "to", "by", "with", "from", "as",
    "vs", "via", "per",
})

_ACRONYM_RE = re.compile(r"^[A-Z][A-Z0-9]+$")


def _normalize_token(token: str, *, is_first: bool) -> str:
    if not is_first and token.lower() in _STOPWORDS:
        return token.lower()
    if _ACRONYM_RE.match(token):
        return token
    if any(c.isupper() for c in token):
        return token
    return token[:1].upper() + token[1:]


def normalize_display_name(name: str) -> str:
    """Normalize a project/task name with title-case + acronym/mixed-case preservation.

    Rules per token (whitespace-split):
      - Connective stopwords (a, the, of, ...) stay lowercase unless first token.
      - All-caps acronyms (>=2 chars) stay as-is.
      - Mixed-case tokens (NuCLEAR, iOS) stay as-is.
      - Otherwise capitalize first letter only.
    Whitespace is collapsed and trimmed; empty input returns "".
    """
    if name is None:
        return ""
    tokens = name.split()
    if not tokens:
        return ""
    out = [_normalize_token(t, is_first=(i == 0)) for i, t in enumerate(tokens)]
    return " ".join(out)
