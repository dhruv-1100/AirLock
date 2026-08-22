"""p_block from the label first-token posterior (SRS §6.5).

Verbalized confidence is systematically biased upward, so the real posterior
comes from top_logprobs over the first token of the "label" value,
renormalised across the nine labels. p_block = 1 − p("BENIGN"),
temperature-scaled by one scalar T.

T resolution order: AIRLOCK_CALIB_T env → results/calibration.json (written by
bench/fit_calibration.py on the Phase 3 dev split) → 1.0. Temperature applies
to the raw label logits: p_T(label) ∝ exp(logit/T).

VERIFY-ON-THE-DAY: all nine labels are believed first-token-distinct; dump the
tokenizer at the 10:45 gate. Fallback if two collide: prefix labels with
distinct digits 1_BENIGN…9_LEGAL_HR and strip in post.
"""

import json
import math
import os

from .schemas import LABELS

_CALIB_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                           "results", "calibration.json")


def _load_T():
    env = os.environ.get("AIRLOCK_CALIB_T")
    if env:
        return float(env)
    try:
        with open(_CALIB_PATH) as f:
            return float(json.load(f)["T"])
    except (OSError, KeyError, ValueError):
        return 1.0


TEMPERATURE = _load_T()


def _label_value_start(text):
    """Char index where the value of the "label" key begins, or -1."""
    k = text.find('"label"')
    if k < 0:
        return -1
    q = text.find('"', text.find(':', k) + 1)
    return q + 1 if q >= 0 else -1


def label_logits_from_logprobs(choice_logprobs):
    """Raw (un-tempered) log-mass per label at the label's first token.

    Returns {label: logprob} for labels with any mass, or raises ValueError.
    This is what bench/fit_calibration.py refits T against — store it once at
    inference time and the whole temperature sweep is offline.
    """
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

    # Mass per label: the candidate token must prefix the label. Real
    # tokenizers hand back leading quotes, spaces, newlines and mixed case
    # here, and a strict match silently matches NOTHING — which sends every
    # call down the verbalized-confidence fallback and saturates the score
    # distribution (INTEGRATION.md §11). Normalise both sides.
    mass = {lb: 0.0 for lb in LABELS}
    for cand in entry["top_logprobs"]:
        tok = cand["token"].strip(' "\n\t\r').upper()
        if not tok:
            continue
        p = math.exp(cand["logprob"])
        for lb in LABELS:
            if lb.startswith(tok):
                mass[lb] += p
    if sum(mass.values()) <= 0:
        raise ValueError("no label mass in top_logprobs")
    return {lb: math.log(m) for lb, m in mass.items() if m > 0}


def p_block_from_logits(logits, T=None):
    """Temperature-scaled p_block from raw label logits, renormalised across
    the nine labels: p_block = 1 − p(BENIGN)."""
    T = T or TEMPERATURE
    mx = max(logits.values())
    exp = {lb: math.exp((lp - mx) / T) for lb, lp in logits.items()}
    total = sum(exp.values())
    return 1.0 - exp.get("BENIGN", 0.0) / total


# How often the real posterior was unavailable and we fell back. This used to
# be silent, which is why a fully-saturated score distribution looked like a
# calibrated one for a whole run.
fallback_count = 0
logprob_count = 0


def p_block_from_logprobs(choice_logprobs, verdict, T=None):
    """Returns (p_block, source) where source is "logprobs" or "verbalized".

    The caller MUST record the source: verbalized confidence is bimodal —
    models state 0.95-0.99 — so a run that silently falls back produces two
    spikes with nothing in between, an inert threshold slider, and an ECE
    computed over two points. Reporting that as a calibrated posterior would
    be reporting a number we did not measure.
    """
    global fallback_count, logprob_count
    try:
        p = p_block_from_logits(label_logits_from_logprobs(choice_logprobs), T)
        logprob_count += 1
        return p, "logprobs"
    except (KeyError, ValueError, TypeError):
        fallback_count += 1
        conf = float(verdict.get("confidence", 0.5))
        p = conf if verdict.get("label", "BENIGN") != "BENIGN" else 1.0 - conf
        return p, "verbalized"
