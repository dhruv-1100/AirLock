# Airlock — where the extension is, and how to show it

## Where it is

`extension/` — load it unpacked. There is no build step and no npm install.

| file | what it does |
|---|---|
| `manifest.json` | MV3. **No `clipboardRead` permission** — the install warning "Read data you copy and paste" is the wrong first impression for a privacy product, and a trusted paste event already carries the data. |
| `airlock.js` | The interceptor. `document_start`, capture phase, all frames. Extracts synchronously, `preventDefault()`, and only replays on `allow`. |
| `overlay.js` | The block card, in a Shadow DOM root: evidence-span underline, receipt, `$rankFusion` scoreDetails tree, `policy_denied` block, streamed local answer, "Mark benign". |
| `console.js` | The in-page live console, bottom-left, collapsible. |
| `sw.js` | The only thing that touches the network. This is not style — `fetch` to `127.0.0.1` from a content script on an `https://` page is subject to Local Network Access; from the service worker it is not. |
| `mainworld.js` | MAIN-world `fetch` patch. Stretch — cut it if anything else is amber. |

---

## Bring-up, in order

Four terminals. Nothing here touches the GPU except the two launch scripts.

```bash
# 1 — models + mongo (once)
bash stack/up_mongo.sh          # wait for MONGO HEAP VERIFIED
bash stack/seed.sh
set -a; . stack/models.env; set +a
bash stack/launch_text.sh       # 0.40   ~4 min, first load
bash stack/launch_vision.sh     # 0.28   total 0.68, ceiling 0.85
bash stack/warm.sh
```

```bash
# 2 — the inspect service. USE THE SCRIPT, it sources models.env for you.
bash stack/run_inspect.sh       # must print CLF_URL=http://127.0.0.1:8000/v1
```

```bash
# 3 — the replica composer (beat 4's stage)
./web/replica/serve.sh          # http://localhost:5173
```

```bash
# 4 — the projector console (no extension needed)
./web/console/serve.sh          # http://localhost:5174
```

## Loading the extension

1. `google-chrome` (151 is installed; the LNA floor is 144.0.7512.0).
2. `chrome://extensions` → **Developer mode** on → **Load unpacked** → select `extension/`.
3. Click the blue **service worker** link on the card and leave that DevTools window open
   all day. Content-script logs go to the *page* console; SW logs go there. Two consoles.
   This trips everyone up once.
4. Open `http://localhost:5173` and paste anything. You should see `[airlock] armed` in
   the page console and `[airlock] sw ping` round-trip.

> **Not yet verified end to end in a real Chrome window.** The extension *loads* — the
> service worker was confirmed running under headless with `--load-extension` — but
> content-script injection could not be confirmed headless, which is a known weak spot
> there. **Do step 4 first and confirm `airlock-root` exists** before relying on it:
> ```js
> // page console on localhost:5173
> !!document.getElementById('airlock-root')   // must be true
> ```
> If it is false, the demo still works on the projector console at :5174 and the
> harness at :5175 — neither needs the extension.

## Demoing without the extension (the fallback that always works)

```bash
python3 -m http.server 5175 --bind 127.0.0.1     # from the repo root
```

| URL | what it shows |
|---|---|
| `http://localhost:5174/` | the live console against the real service — decisions, FPR/recall, KV gauges |
| `…:5175/tools/harness/#evidence` | the block card with the evidence span underlined |
| `…:5175/tools/harness/#no-model` | the cascade strip: "no model was called" |
| `…:5175/tools/harness/#image-ocr` | beat 3's card with the model's transcript |
| `…:5175/tools/harness/#slider` | the threshold slider mid-drag |

Screenshots of the first two are already in `screenshots/`.

## The beats, and what actually works today

| beat | state |
|---|---|
| 1 · customer list blocks | works — T2, ~1.7 s, evidence span underlined |
| 2 · benign question allows | works — `allow BENIGN` at T2 |
| 3 · chart blocks | **does not block yet.** The chart transcribes correctly, then returns `allow BENIGN` with zero evidence spans, so span verification forces BENIGN. And T3 is 10–20 s against a 2500 ms client abort. See `results/t3_latency.md`. Use `gate_01.png`, which does block. |
| 4 · detector learns | untested end to end |
| 5 · `policy_denied` | works — `evidence/policy-denied.json`, all four cloud LLM hosts 403 |
| offline · unplug | `stack/proof.sh`. **Run it on `localhost:5173`, never with the `chatgpt.com` tab focused** — one reload offline and that tab is gone. |

## Before you rehearse

```bash
# beat 3's ALLOW is cached by payload hash and will replay in 1 ms
mongosh "mongodb://localhost:27017/?directConnection=true" \
  --eval 'db.decisions.deleteMany({modality:"image"})'
```
