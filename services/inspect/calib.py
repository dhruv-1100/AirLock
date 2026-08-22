"""p_block from the label first-token posterior (SRS §6.5).

Verbalized confidence is systematically biased upward, so the real posterior
comes from top_logprobs over the first token of the "label" value,
renormalised across the nine labels. p_block = 1 − p("BENIGN"),
temperature-scaled by one scalar T. T=1.0 until the Phase 3 calibration fit
(scipy minimize_scalar on a 200-item dev split, minimising NLL).

VERIFY-ON-THE-DAY: all nine labels are believed first-token-distinct; dump the
tokenizer at the 10:45 gate. Fallback if two collide: prefix labels with
distinct digits 1_BENIGN…9_LEGAL_HR and strip in post.
"""

import math

from .schemas import LABELS

TEMPERATURE = 1.0  # Phase 3 fits this; do not hand-tune.


def _label_value_start(text):
    """Char index where the value of the "label" key begins, or -1."""
    k = text.find('"label"')
    if k < 0:
        return -1
    q = text.find('"', text.find(':', k) + 1)
    return q + 1 if q >= 0 else -1


def p_block_from_logprobs(choice_logprobs, verdict, T=None):
    """choice_logprobs: OpenAI-shape list of {token, logprob, top_logprobs}.

    Falls back to the verbalized confidence when the logprob walk fails —
    logged upstream, never fatal.
    """
    T = T or TEMPERATURE
    try:
        full = "".join(e["token"] for e in choice_logprobs)
        start = _label_value_start(full)
        if start < 0:
            raise ValueError("label key not found in generation")
        pos = 0
        entry = None
        for e in choice_logprobs:
            end = pos + len(e["token"])
            if pos <= start < end:
                entry = e
                break
            pos = end
        if entry is None or not entry.get("top_logprobs"):
            raise ValueError("no top_logprobs at label position")

        # Mass per label: candidate token (sans leading quote/space) must be a
        # prefix of the label. Renormalise across the nine labels only.
        mass = {lb: 0.0 for lb in LABELS}
        for cand in entry["top_logprobs"]:
            tok = cand["token"].lstrip(' "')
            if not tok:
                continue
            p = math.exp(cand["logprob"] / T)
            for lb in LABELS:
                if lb.startswith(tok):
                    mass[lb] += p
        total = sum(mass.values())
        if total <= 0:
            raise ValueError("no label mass in top_logprobs")
        return 1.0 - mass["BENIGN"] / total
    except (KeyError, ValueError, TypeError):
        conf = float(verdict.get("confidence", 0.5))
        return conf if verdict.get("label", "BENIGN") != "BENIGN" else 1.0 - conf
