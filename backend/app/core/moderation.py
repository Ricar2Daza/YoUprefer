import re
from typing import Iterable


_DISALLOWED_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bincest\b",
        r"\bpedo(?:filia|philia)?\b",
        r"\bchild\s*porn\b",
        r"\bcp\b",
        r"\brape\b",
        r"\bviolaci[oó]n\b",
        r"\bgore\b",
        r"\bdecap(?:itation|itaci[oó]n)\b",
        r"\bdismember(?:ment)?\b",
        r"\bnecrophil(?:ia|ic)\b",
        r"\bbestial(?:ity|ismo)\b",
        r"\bzoofil(?:ia|ico)\b",
        r"\bporn(?:o|ografia|ography)?\b",
        r"\bxxx\b",
        r"\bnude(?:z|s)?\b",
        r"\bdesnude(?:z|s)?\b",
        r"\bsexo\b",
        r"\bsexual\b",
    )
)


def find_disallowed(text: str | None) -> str | None:
    if not text:
        return None
    for rx in _DISALLOWED_PATTERNS:
        if rx.search(text):
            return rx.pattern
    return None


def validate_text(text: str | None, *, fields: Iterable[str] = ()) -> None:
    found = find_disallowed(text)
    if found:
        field_label = ", ".join(fields) if fields else "texto"
        raise ValueError(f"Contenido no permitido en {field_label}")

