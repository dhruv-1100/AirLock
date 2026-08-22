# CONTRACT.md — frozen 10:00, immutable for the day

The `airlock.inspect.v1` request and `airlock.verdict.v1` response bodies below are pasted
verbatim from SRS §5.1. Every mock, fixture and stub in the plan conforms to this file.
Nobody waits on anybody because of a field name.

Base URL: `http://127.0.0.1:8787` (all services bind `127.0.0.1`).
The Chrome extension talks **only** to this origin, and **only from the service worker**
(MV3 / Local Network Access constraint). `https://inference.local` is a sandbox-side name
and must never appear in the extension.

---

## `POST /v1/inspect` — request (`airlock.inspect.v1`)

`Content-Type: application/json`, max body 8 MiB.

```json
{
  "schema": "airlock.inspect.v1",
  "request_id": "r_9f3a2c",
  "ts": 1755772800123,
  "origin": "https://chatgpt.com",
  "url": "https://chatgpt.com/c/abc",
  "text": "…paste text, may be \"\"…",
  "html": "",
  "images": [ { "mime": "image/jpeg", "w": 1280, "h": 720, "b64": "/9j/4AAQ…" } ],
  "mode": "balanced",
  "threshold": null
}
```

Rules:
- `images` ≤ 1 (extension enforces; server rejects > 4 with `413`).
- `b64` is raw base64, **no** data-URI prefix.
- Client downscales long edge ≤ **1024 px** *before* send. (B → A: the sweep must use the
  same input distribution: long edge 1024, JPEG q=0.82.)
- `mode` ∈ `audit` | `balanced` | `strict`.

## `POST /v1/inspect` — response `200` (`airlock.verdict.v1`)

```json
{
  "schema": "airlock.verdict.v1",
  "request_id": "r_9f3a2c",
  "action": "block",
  "label": "CUSTOMER_RECORD",
  "severity": "HIGH",
  "policy_clause_id": "POL-004",
  "policy_clause_text": "Customer-identifying records must not leave managed endpoints.",
  "reason": "12 rows of name,email,phone,plan,mrr",
  "evidence_spans": ["ana.ruiz@northwind.example,+1-415-555-0142,Pro,4200"],
  "evidence_verified": true,
  "score": 0.94,
  "p_block": 0.94,
  "threshold": 0.55,
  "tier": "T2",
  "model": "airlock-clf/qwen3-4b",
  "modality": "text",
  "latency_ms": 312,
  "bytes_egressed": 0,
  "decision_id": "6712c0f1a3e94b2d8c5e1102",
  "score_details": { "value": 0.0306, "description": "reciprocal rank fusion…", "details": [] }
}
```

- `action` ∈ `allow` | `block` | `warn`
- `tier` ∈ `T0` | `T1` | `T2` | `T3` | `CACHE`
- On `allow`: `label:"BENIGN"`, `evidence_spans: []`, `severity:"NONE"`.

## Status codes

| Code | Meaning |
|---|---|
| `200` | verdict — **including block**. A block is not an HTTP error. |
| `400` | malformed JSON / missing `schema` |
| `413` | body > 8 MiB or > 4 images |
| `422` | image decode failure |
| `429` | > 32 in-flight |
| `503` | classifier not ready (model loading) |
| `504` | upstream vLLM exceeded 2000 ms |

## Error shape (all non-200) — `airlock.error.v1`

```json
{ "schema":"airlock.error.v1", "error":"policy_denied", "code":503,
  "label":"airlock_unavailable", "action":"block",
  "reason":"Inspector unreachable — deny by default", "request_id":"r_9f3a2c" }
```

`"error":"policy_denied"` is deliberate: byte-identical to OpenShell's egress-denial body.

## Timeouts

- Client `AbortController` **2500 ms** → renders fail-closed BLOCK.
- Server internal budget: T1 5 ms, T2 call 1200 ms, T3 call 2000 ms, hard total 2300 ms.
- Server never hangs; it returns `504` with the fail-closed body.

---

## Supporting endpoints

| Method | Path | 200 body | Notes |
|---|---|---|---|
| `GET` | `/healthz` | `{"ok":true,"clf":true,"vlm":true,"mongo":true,"uptime_s":812}` | Any `false` ⇒ still `200`; extension shows amber dot. SW warms this on `onStartup`. |
| `GET` | `/v1/policy` | `{"version":"policy_v1","clauses":[{"id":"POL-001","class":"CREDENTIAL","severity":"HIGH","text":"…"}]}` | Clause text for the overlay. |
| `GET` | `/v1/decisions?limit=50` | `{"decisions":[ …projection of `decisions`, `evidence_png` excluded… ]}` | Console backfill, then tail over the WS. |
| `POST` | `/v1/answer` | SSE stream, OpenAI chat delta shape | Sanctioned path. `{"prompt":"…","decision_id":"…"}` → proxies `:8000`. |
| `POST` | `/v1/feedback` | `{"ok":true,"corpus_id":"…","embedded":true}` | `{"decision_id":"…","verdict":"benign","analyst":"demo"}` |
| `GET` | `/v1/report` | `{"n":1000,"false_pos":3,"fpr":0.003,"ci95":[0.001,0.0088],"p50_ms":12,"p95_ms":480,"by_class":{…}}` | From the `benign_eval` aggregation. |
| `OPTIONS` | any | `204` | `Access-Control-Allow-Origin: *`, `-Methods: POST, GET, OPTIONS`, `-Headers: Content-Type`, `Access-Control-Allow-Private-Network: true`, `-Max-Age: 600`. Use with `credentials: 'omit'`. |

## WebSocket console — `ws://127.0.0.1:8787/v1/stream`

Server→client only. Client may send one optional first frame `{"type":"hello","since":"<resume_token>"}`.
One JSON object per frame, newline-free.

```json
{"type":"decision","ts":1755772800123,"decision_id":"6712c0f1…","host":"chatgpt.com",
 "modality":"text","chars":412,"action":"allow","label":"BENIGN","p_block":0.02,
 "tier":"T1","latency_ms":188}
```

Other frames:
- `{"type":"hello","policy_version":"policy_v1","resume":"<token>"}` on connect
- `{"type":"metric","kv":{"kv_cache_text":0.31,"kv_cache_vision":0.12,"escalation_rate":0.14}}` every 2 s
- `{"type":"ping"}` every 15 s

Client reconnects with exponential backoff 250 ms → 4 s.
