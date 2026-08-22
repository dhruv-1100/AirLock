# Extension — verified end to end for the first time, and one bug left

Verified by loading `extension/` through CDP `Extensions.loadUnpacked` (Chrome 151 no
longer honours `--load-extension` from the command line — the flag is silently ignored
and the extension never reaches the registrar) and driving the replica page at
`localhost:5173`.

## Proven working

| check | result |
|---|---|
| content script injects | `!!document.getElementById('airlock-root')` → **true** |
| overlay shadow root builds | console panel present |
| **service-worker transport** | console backfilled **50 rows** via `viaWorker('DECISIONS')` → `GET /v1/decisions` |
| SW can reach the inspector | `fetch('http://127.0.0.1:8787/healthz')` from inside the SW → **HTTP 200** |
| **paste is intercepted** | `preventDefault()` **fired** on the customer-list paste |
| **payload never reaches the page** | composer `innerText` is `''` after the block — this is what makes `bytes_egressed: 0` literal |
| fail-closed card renders | title, severity chip, receipt, all correct |

That is the core claim of the product demonstrated rather than asserted: the characters
were removed from the event and the page never saw them.

## The one bug left

**`INSPECT` specifically never reaches the server.** The verdict comes back
`airlock_unavailable` in **0 ms** and the server-side counter does not move
(1450 POSTs before, 1450 after). Everything else on the same transport works — the
console backfill goes through `chrome.runtime.sendMessage` to the same service worker
and succeeds, and the SW's own `fetch` to `:8787` succeeds.

So it is not the transport, not host permissions, and not the inspector being down. It
is something specific to the `INSPECT` path in `airlock.js` → `sw.js`. 0 ms rules out a
timeout: `viaWorker()` is rejecting immediately and `direct()` is failing immediately
after it.

**Where to look first**, in order:
1. `viaWorker()`'s `orphaned()` guard — `chrome.runtime.id` access throwing would reject
   instantly and look exactly like this.
2. Whether the `INSPECT` branch in the `sw.js` `onMessage` switch is reached at all —
   put a `console.log` at the top of the listener and watch the **service worker**
   DevTools window, not the page console.
3. The service worker being idle-killed between page load and paste. The console
   backfill happens at load, the paste happens later; if waking on `INSPECT` is where it
   breaks, that is the difference between the two paths.

**Caveat on the test itself:** the paste was dispatched as a synthetic `ClipboardEvent`
with a real `DataTransfer` from the page world, so `isTrusted` is `false`. Our handler
does not check `isTrusted`, which is why it fired — but a human pressing ⌘V is a
*trusted* event and may behave differently. **Someone should still do one manual paste**
and watch the service-worker console.

## Not a bug

`SW ping: {}` in my test output is an artifact — CDP `Runtime.evaluate` runs in the
page's MAIN world, where `chrome.runtime.sendMessage` does not exist. It is not evidence
about the extension's messaging.
