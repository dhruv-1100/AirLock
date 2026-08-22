# submission/airlock-demo.mp4 — 64 s, 1600×934, no audio

Screen recording of the real system on the box. **The pastes are real** — driven through
the loaded extension into the replica composer, and each one hit `/v1/inspect` on the
live service (the request counter moved 1452 → 1454 during the take).

| t | scene | what it shows |
|---|---|---|
| 0–22 s | **beat 1 — customer list blocked** | a real paste. "Blocked before it left this machine", HIGH · CUSTOMER_RECORD, POL-004 cited, the Ana Ruiz row **underlined verbatim in the payload**, receipt reading `bytes egressed 0`, and the cascade strip lighting CACHE with T0/T1/T2/T3 dark — *"No model was called."* The composer stays empty: the characters never reached the page. |
| 22–34 s | **beat 2 — benign question** | a real paste of a Python question, allowed |
| 34–48 s | **live console** | decisions off the change stream, FPR 4.00% / recall 87.8% / n 1000, KV gauges scraped from both vLLM `/metrics` |
| 48–64 s | **policy evidence** | four cloud LLM hosts returning `403 policy_denied` from inside the sandbox; every inference request routed to one endpoint, the local 30B |

## Honest notes

- Beat 1 resolved from the **hash cache** (`tier: CACHE`, `<1 ms`) because the same
  payload had been inspected during testing. That is a real Airlock behaviour — the
  second identical paste blocks with no model call — but if you want the T2 path on
  screen instead, clear the cache first:
  `db.decisions.deleteMany({})`, then re-record.
- The paste is dispatched as a synthetic `ClipboardEvent` carrying a real `DataTransfer`,
  because the recording is driven over CDP. Our handler does not check `isTrusted`, so it
  takes the same path a human ⌘V does — but a human ⌘V has still not been tested.
- Beat 3 (image) is not in this cut: it does not block yet.
- Regenerate: load the extension via CDP `Extensions.loadUnpacked` (Chrome 151 ignores
  `--load-extension`), open the page **after** the extension is loaded, and record `:1.0`.
