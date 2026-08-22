# Developer B — Client & UI · working notes

Branch `dev_B_RS`. Owns `extension/**`, `web/replica/**`, `web/console/**`, and
`tools/stub_inspect.py`. Never touches anything with `--gpus`, any `vllm serve`, any
bare `python` that imports torch, MongoDB indexes, or the policy artifact (NFR-S1).

Contract is `CONTRACT.md`, frozen. Everything below conforms to it.

---

## Run it

Three terminals, none of which touch the GPU.

```bash
# 1 — the inspector. Kill this the moment A says :8787 is real. Same port, same contract.
python3 -m venv .venv && ./.venv/bin/pip install fastapi 'uvicorn[standard]' websockets
./.venv/bin/uvicorn tools.stub_inspect:app --host 127.0.0.1 --port 8787
```

```bash
# 2 — the replica composer, beat 4's stage
./web/replica/serve.sh          # http://localhost:5173
```

```bash
# 3 — the projector console (standalone, no extension needed)
./web/console/serve.sh          # http://localhost:5174
```

Load the extension: `chrome://extensions` → Developer mode → Load unpacked →
`extension/`. Open the blue **service worker** link on the extension card and leave
that DevTools window open all day. Content-script logs go to the *page* console; SW
logs go to that one. Two consoles — this trips people up every single time.

### Styling the overlay without reloading the extension

```bash
python3 -m http.server 5175 --bind 127.0.0.1     # from the repo root
```
then open `http://localhost:5175/tools/harness/`. It loads `extension/overlay.js` and
`extension/console.js` directly against `tools/fixtures/*.json`, with `chrome.*` and
the transport stubbed. Buttons for: block card, allow chip, fail-closed card, scanning
chip, and 40 synthetic decisions into the console feed. Normal page refresh, no
orphaned content scripts.

---

## What is where

| File | What it is |
|---|---|
| `extension/manifest.json` | MV3. **No `clipboardRead`** — the install warning "Read data you copy and paste" is the wrong first impression for a privacy product, and we do not need it: a trusted `paste` event already carries the data. |
| `extension/airlock.js` | The interceptor. ISOLATED world, `document_start`, `all_frames`, capture phase. |
| `extension/overlay.js` | Shadow-DOM UI: scanning chip, block card, evidence highlight, receipt, `scoreDetails` tree, `policy_denied` block, sanctioned-answer panel. |
| `extension/console.js` | The in-page live console panel, bottom-left, collapsible. Threshold slider, mode dropdown, KV gauges, lockdown toggle. |
| `extension/sw.js` | The only thing that touches the network. `/v1/inspect`, the WebSocket, the SSE relay, the `declarativeNetRequest` lockdown rule. |
| `extension/mainworld.js` | MAIN-world `fetch` patch. **Stretch — cut at 16:00 without hesitation if anything else is amber.** |
| `extension/scores_benign.json` | **PLACEHOLDER.** Shape only. Overwrite with `results/scores_benign.json` the moment A produces it. The console labels it as a placeholder until you do. |
| `web/replica/` | `localhost:5173`. Beat 4's stage. |
| `web/console/` | `localhost:5174`. Standalone projector console — works with no extension at all. |
| `tools/stub_inspect.py` | B's inspector. Full contract: inspect, healthz, policy, decisions, feedback, report, SSE answer, WebSocket stream, CORS with `Access-Control-Allow-Private-Network`. |
| `tools/harness/` | Fixture-driven overlay dev page. |

---

## The five rules that cost the most time when broken

1. **`return true` at the end of every `chrome.runtime.onMessage` listener.** Without
   it `sendResponse` is discarded, the content script times out at 2500 ms, and the
   overlay renders a fail-closed BLOCK. It looks exactly like a wedged GPU. Check this
   before you suspect A.
2. **Nothing may `await` above `preventDefault()`.** The default action of a trusted
   paste runs the moment the handler returns. One `await` and the payload is in the
   composer. Extraction of `text/plain`, `text/html` and `items[].getAsFile()` is all
   synchronous for this reason.
3. **`fetch()` to `127.0.0.1` happens in the service worker, never in the content
   script.** From an `https://` page the content script is subject to Local Network
   Access; the service worker is not. `direct()` with `targetAddressSpace:'local'`
   exists only as a fallback for when the extension context has been invalidated.
4. **Never assign `.value`, never dispatch a synthetic `ClipboardEvent`.** React reads
   its own shadow copy of `value`, so a direct assignment updates the DOM and not the
   component. A synthetic ClipboardEvent is `isTrusted:false`, performs no default
   action, and fails silently. Replay goes through `document.execCommand('insertText')`
   with `setNativeValue()` (prototype setter + `input` event) as the fallback.
5. **Bind to `document`, never to a selector.** ProseMirror and Lexical rebuild their
   nodes constantly; a selector-bound listener ends up on a node that no longer exists.

## Fail-closed, everywhere

Every throw in `gate()` lands on `{action:'block', label:'airlock_unavailable'}`.
Timeout, unreachable service, orphaned extension context, undecodable image, malformed
verdict body, MAIN-world bridge silence past 3000 ms — all BLOCK. Deny-by-default is
the product, so it has to be the failure mode too. A wedged backend on stage produces a
block screen, not a dead demo.

The one place the UI deliberately does *not* pretend: if the verdict's
`evidence_spans` are not literal substrings of the payload, the card says so in the
note under the evidence block rather than rendering a plain payload as if it had been
highlighted. Span verification is only worth anything if it is visibly checkable.

---

## Handoffs

**B → A**
- Client downscale is **long edge 1024 px, JPEG q=0.82**, base64 without the data-URI
  prefix. Run the vision latency sweep on that exact input distribution.
- Client `AbortController` fires at **2500 ms** and renders a BLOCK. Anything slower
  than that is invisible to the demo, so the server-side budget has to stay under it.
- Extension sends at most **one** image per request.
- Drop `tools/fixtures/verdict_block.json` / `verdict_allow.json` replacements any time
  the real shape of `evidence_spans` or `score_details` moves; the overlay renders from
  those files in the harness.
- Send `results/scores_benign.json` as `{"benign":[…p_block…],"sensitive":[…]}`; it goes
  straight over `extension/scores_benign.json` and `web/console/scores_benign.json`.

**B → C**
- The block card renders `policy_clause_id` + `policy_clause_text` verbatim from the
  verdict, which comes from C's `policy.yaml`. Clause text under ~180 characters reads
  well in the card; longer wraps to four lines and starts to look like fine print.
- `scoreDetails` is rendered as a table of `inputPipelineName` / `rank` / `weight` /
  `value` plus the server's own `description`. The client-side `rrf(k=60)` fallback
  emits the identical shape, so swapping the backend needs no change here.
- Screenshots for the submission come out of the harness at final quality — block card,
  evidence highlight, `scoreDetails` expanded, console with the feed scrolled, slider
  mid-drag. Due to C by 15:40.

---

## Gate checklist

- **G1-B, 10:45 — browser transport.** `chrome://version` ≥ 144.0.7512.0 (record it; if
  142.x/143.x, either `chrome://flags#local-network-access-check → Disabled` and
  relaunch, or launch with `--user-data-dir=/tmp/airlock-profile` — note which was
  needed). Load unpacked, open `https://chatgpt.com`, confirm `[airlock] sw ping` in the
  page console. That single line proves the LNA-exempt service-worker path works on this
  box and de-risks everything downstream.
- **G2, 12:30 — end-to-end text block.** Paste the customer list into a real composer;
  the card renders, the characters never appear in the composer, `bytes egressed: 0`.
  Against the stub is a conditional pass if A is late (risk R3).
- **G3, 14:30 — all three beats.** Text block, benign pass-through, image block.
- **G5, 16:30 — demo freeze.** Reload the extension, reload every tab, then do not touch
  `chrome://extensions` again. Pre-open tabs in demo order. Fire one warm-up paste of
  each modality. Payloads in a scratch file on screen 2 — never type on stage.

**Fallback (R6, deadline 12:50):** if a site handler wins the paste, move every beat to
`localhost:5173`. Loopback→loopback removes LNA entirely and no framework is fighting
for the event. Cost is one pitch line, not the demo.

**Never unplug the ethernet while a `chatgpt.com` tab is focused** (R15). Beat 4 runs on
`localhost:5173`, rehearsed with the cable actually out.
