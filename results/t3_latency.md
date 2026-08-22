# T3 image path — first end-to-end run (item 8)

Never exercised before today. It works, and three things about it break beat 3 as
scripted. Measured against the live `airlock-vision` (Nemotron-3-Nano-Omni-30B BF16)
through `/v1/inspect`, seed images from `bench/make_images.py --all --seed 1337`.

| image | verdict | latency | evidence spans |
|---|---|---|---|
| `fy26_forecast.png` (first call) | `allow BENIGN` | **12,995 ms** | 0 |
| `fy26_forecast.png` (second call) | `allow BENIGN` | 1 ms — **CACHE** | 0 |
| `gate_00.png` | 504 | 19,909 ms | — |
| `gate_01.png` | `block FINANCIAL_NONPUBLIC` | **10,013 ms** | 1 |

## 1. Latency is 10–20 s, not the 2.0 s SRS §5.1 budgeted

§7.1 already flagged NFR-L4 as "derived arithmetic, not measurement… the single largest
unverified number in the project". It was derived for **Holo1.5-7B**. The model actually
on the box is a **30B** multimodal — roughly four times the parameters.

Consequence for the demo: B's client `AbortController` fires at 2500 ms, so a real
browser paste of an image **always** fail-closes to BLOCK. The block card appears, which
looks like beat 3 working — but it is the `airlock_unavailable` card, not a verdict. The
reason line reads "Inspector exceeded 2500 ms — deny by default" rather than quoting the
chart. A judge who reads the card will see it.

`T3_TIMEOUT_S` is now env-driven (`AIRLOCK_T3_TIMEOUT_S`, default unchanged at 2.0).

## 2. The demo chart transcribes correctly but is forced BENIGN

The vision model read it right:

```
extracted_text: ['FY26 Revenue Forecast — Plan vs. Commit', 'Plan', 'Commit',
                 'Revenue (USD, millions)', '0', ...]
reason: "The chart contains financial vocabulary ('Revenue (USD, millions)') and
         forward-looking temporal markers ('FY26', 'Q1 2025', etc.), meeting the
         criteria for FIN…"
```

…and then returned `allow BENIGN` with **zero evidence spans**. The model described its
markers in prose instead of populating `evidence_spans`, so §7.4's span-verification
fail-open fired and forced BENIGN. That is the mechanism working exactly as designed —
it refused to block on something it could not point at — but it means **beat 3 does not
block on the intended image**.

`gate_01.png` did block (`FINANCIAL_NONPUBLIC`, 1 span), so the path is sound. This is a
prompt/schema-adherence problem with this model, not a broken tier.

## 3. The ALLOW is now in the instant-block cache

Second call returned in 1 ms from `decisions.payload_sha256`. Re-pasting the same chart
replays the cached ALLOW. Before rehearsing beat 3, clear it:

```bash
mongosh "mongodb://localhost:27017/?directConnection=true" \
  --eval 'db.decisions.deleteMany({modality:"image"})'
```

## What I would do

1. **Do not rehearse beat 3 until the chart actually blocks.** Either tighten the T3
   prompt so markers land in `evidence_spans` (A owns `t3.py`), or swap the demo image
   for one that already blocks — `gate_01.png` does.
2. **Decide honestly what to say about latency.** 10–20 s is not an interactive path
   with this model. Options: state it as measured and frame the image path as
   asynchronous; or drop to a smaller VLM. Do not show a 2.5 s fail-closed card and
   describe it as the model's verdict.
3. NFR-L4's 10:45 gate criterion (p50 ≤ 1.5 s, p95 ≤ 2.5 s) **fails** on this model.
   That is a measurement, and it is the first one anyone has taken.
