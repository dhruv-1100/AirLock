"""Tier 0 — trivial gate (SRS §6.4, NFR-L1).

len < 40 and no digit and none of {@ : / =}  →  ALLOW without any further work.
"""

_FORBIDDEN = set("@:/=")


def is_trivial(text: str) -> bool:
    if len(text) >= 40:
        return False
    if any(c.isdigit() for c in text):
        return False
    return not (_FORBIDDEN & set(text))
