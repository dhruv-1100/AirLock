# submission/airlock-demo.mp4 — 62 s, 1600×980, no audio

Screen recording of the real system on the box, not a mockup. §14 lists a short capture
as optional insurance against a live-demo failure; this is it.

| t | scene | what is real in it |
|---|---|---|
| 0–14 s | **live console** at `localhost:5174` | decisions streaming from MongoDB over the change stream; `clf ✓ vlm ✓ mongo ✓`; **FPR 4.00%**, **recall 87.8%**, n **1000** from the measured run; KV-cache gauges scraped live from both vLLM `/metrics` |
| 14–29 s | **block card** | evidence span underlined verbatim in the payload, the `<dl>` receipt, MongoDB `$rankFusion` scoreDetails expanded, and the `policy_denied` body the extension renders |
| 29–38 s | **cascade strip** | the stage that did *not* run — "No model was called. Resolved deterministically at T1 on CPU" |
| 38–48 s | **image path** | the FY26 chart with the vision model's own transcript, markers underlined in it |
| 48–62 s | **policy evidence** | all four cloud LLM hosts returning `403 policy_denied` from inside the sandbox, and every inference request routing to one endpoint — the local 30B |

## Honest notes, so nobody is caught out

- The overlay scenes are driven from `tools/harness/` against `tools/fixtures/*.json`, not
  from a live paste. The card, the evidence highlight, the scoreDetails tree and the
  cascade are the real components rendering real verdict shapes; the paste that produced
  them is a fixture. **Do not narrate this as a live paste.**
- The console, the numbers, the KV gauges and the policy evidence are all live.
- Beat 3 still does not block on the demo chart — the card shown is the transcript view.
- Regenerate: `bash stack/run_inspect.sh`, `./web/console/serve.sh`,
  `python3 -m http.server 5175`, then record `:1.0` with ffmpeg while walking the URLs
  in the table above.
