# submission/airlock-demo.mp4 — 121 s, 1600×934, no audio

Screen recording of the real system on the box. **Every paste is real** — dispatched
into the replica composer through the loaded extension, each one hitting `/v1/inspect`
on the live service. The decision cache was cleared first, so beat 1 is a genuine T2
inference and not a replay.

| t | scene | what it shows |
|---|---|---|
| ~20–50 s | **beat 1 — customer list blocked at T2** | "Blocked before it left this machine", HIGH · CUSTOMER_RECORD, POL-004 cited, the Ana Ruiz row **underlined verbatim in the payload**, `bytes egressed 0`, and the cascade strip with CACHE / T0 / T1 lit and **T2 carrying the decision at ~2.9 s**. The composer stays empty — the characters never reached the page. |
| ~50–58 s | **`$rankFusion` scoreDetails** | expanded: per-pipeline rank, weight and contribution, with MongoDB's own description of the RRF formula |
| ~58–80 s | **the sanctioned path** | "Answer this on the local model instead" — the blocked question re-answered, streamed token by token from the 30B on this box |
| ~80–90 s | **beat 2 — benign question allowed** | the text is **replayed into the composer**, which is the allow path working visibly |
| ~90–100 s | **the instant-block cache** | the same customer list pasted again — blocked in ~1 ms at `tier: CACHE`, no model call |
| ~100–115 s | **live console** | decisions off the MongoDB change stream, FPR 4.00% / recall 87.8% / n 1000, KV gauges scraped from both vLLM `/metrics` |
| ~115–121 s | **policy evidence** | four cloud LLM hosts returning `403 policy_denied` from inside the sandbox; every inference request routed to one endpoint — the local 30B |

## Honest notes

- The paste is a synthetic `ClipboardEvent` carrying a real `DataTransfer`, because the
  recording is driven over CDP. Our handler does not check `isTrusted`, so it takes the
  same path a human ⌘V does — **but a human ⌘V has still not been tested.**
- Beat 3 (image) is not in this cut. It does not block yet: the chart transcribes
  correctly and then returns `allow BENIGN` with no evidence spans, so span verification
  forces BENIGN. See `results/t3_latency.md`.
- The console's feed is topped up by `tools/fake_decisions.py` so it looks like a working
  day; the FPR, recall, n and KV gauges on that screen are all real.

## Regenerate

Chrome 151 ignores `--load-extension`, and `--app` windows do not run content scripts.
Load via CDP `Extensions.loadUnpacked`, then open the page **after** the extension is
loaded (an already-open tab never gets the content script, even on a hard reload), then
record `:1.0` with ffmpeg. Clear `db.decisions` first or beat 1 replays from cache.
