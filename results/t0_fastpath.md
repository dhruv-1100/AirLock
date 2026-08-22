# T0 fast-path probe — the other half of the escalation story

Run by B against the live service during bring-up, using C's `data/shortpaste_v1.jsonl`
(n=40, 15–35 chars, authored specifically to exercise T0).

```
n = 40      tier mix: {'T0': 40}
resolved WITHOUT a model call: 40/40 = 100.0%
p50 4.8 ms    p95 6.7 ms      (includes the HTTP round trip)
```

## Why this matters, and what it does and does not license

The 1000-item benign run escalated **99.8%** to T2. This probe escalates **0%**. Neither
number is "the" escalation rate — each is a property of its corpus:

| corpus | char range | reaches a model |
|---|---|---|
| `benign_v1` (1000, real, six sources) | 200–3964 | 99.8% |
| `shortpaste_v1` (40, authored probe) | 15–35 | 0% |

T0's gate is `len < 40` with no digit and none of `@ : / =`. `benign_v1` has a 200-char
floor, so **T0 cannot fire on it by construction** — that is a corpus property, not a
detector result. Equally, a 40-item authored probe is not a denominator.

**What we can say:** the fast path works and costs ~5 ms end to end, and the FPR of
6.90% is conservative precisely because every one of those 1000 items reached the model —
nothing was waved through by a cheap gate.

**What we cannot say:** any blended escalation rate, blended latency, or seats-per-box
figure. Those need a paste-length distribution measured from real usage, which we do not
have. Quoting "~14% escalate" from either corpus would be inventing a number.

NFR-L1 targets p50 ≤ 1 ms and p95 ≤ 3 ms in-process; the 4.8/6.7 ms here is measured
over HTTP from a separate process and includes the round trip, so it is not directly
comparable to the in-process budget.
