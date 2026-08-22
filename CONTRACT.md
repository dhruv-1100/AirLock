# CONTRACT.md — frozen 10:05, immutable for the day

Per SRS §10 contract freeze. The bodies below are pasted verbatim from SRS §5.1 and are
**immutable**. Every mock, fixture and stub in the plan conforms to this file.
Nobody waits on anybody because of a field name.

Owners: **A** produces the verdict · **B** consumes it · **C** persists it.

> **Reconciled with B's copy on `dev_B_RS`.** B and C independently wrote this file.
> Every JSON field name, status code, timeout and frame type agrees between the two —
> checked field-by-field, not eyeballed. This version is a superset: it adds the port
> ownership table and the NFR-S1 reminder at the end. **Take this one at merge.**

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
- `images` ≤ 1 (extension enforces; server rejects >4 with `413`).
- `b64` is raw base64, **no data-URI prefix**.
- Client downscales long edge ≤ 1024 px **before** send. (B → A: max edge is **1024**.)

---

## `POST /v1/inspect` — response 200 (`airlock.verdict.v1`)

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

Enumerations:
- `action` ∈ `allow` | `block` | `warn`
- `tier` ∈ `T0` | `T1` | `T2` | `T3` | `CACHE`
- `label` ∈ `BENIGN` | `CREDENTIAL` | `PAYMENT_CARD` | `GOV_ID` | `CUSTOMER_RECORD` |
  `HEALTH_RECORD` | `FINANCIAL_NONPUBLIC` | `PROPRIETARY_CODE` | `LEGAL_HR`
- `severity` ∈ `NONE` | `LOW` | `MEDIUM` | `HIGH`
- `policy_clause_id` ∈ `NONE` | `POL-001` … `POL-009`

On `allow`: `label:"BENIGN"`, `evidence_spans: []`, `severity:"NONE"`.

---

## Status codes

| Code | Meaning |
|---|---|
| `200` | verdict — **including block. A block is not an HTTP error.** |
| `400` | malformed JSON / missing `schema` |
| `413` | body > 8 MiB or > 4 images |
| `422` | image decode failure |
| `429` | > 32 in-flight |
| `503` | classifier not ready (model loading) — fail-closed body |
| `504` | upstream vLLM exceeded 2000 ms |

## Error shape — all non-200 (`airlock.error.v1`)

```json
{ "schema":"airlock.error.v1", "error":"policy_denied", "code":503,
  "label":"airlock_unavailable", "action":"block",
  "reason":"Inspector unreachable — deny by default", "request_id":"r_9f3a2c" }
```

The `"error":"policy_denied"` string is **deliberate and load-bearing**: it is byte-identical
to OpenShell's egress-denial body, which is demo beat 5. Do not "clean it up".

---

## Timeouts

- Client `AbortController` **2500 ms** → renders fail-closed BLOCK.
- Server internal budget: T1 5 ms · T2 call 1200 ms · T3 call 2000 ms · hard total 2300 ms.
- Server never hangs; it returns `504` with the fail-closed body.

---

## Supporting endpoints (SRS §5.2)

| Method | Path | 200 body |
|---|---|---|
| `GET` | `/healthz` | `{"ok":true,"clf":true,"vlm":true,"mongo":true,"uptime_s":812}` |
| `GET` | `/v1/policy` | `{"version":"policy_v1","clauses":[{"id":"POL-001","class":"CREDENTIAL","severity":"HIGH","text":"…"}]}` |
| `POST` | `/v1/answer` | SSE stream, OpenAI chat delta shape. Body `{"prompt":"…","decision_id":"…"}` |
| `POST` | `/v1/feedback` | `{"ok":true,"corpus_id":"…","embedded":true}`. Body `{"decision_id":"…","verdict":"benign","analyst":"demo"}` |
| `GET` | `/v1/report` | `{"n":1000,"false_pos":3,"fpr":0.003,"ci95":[0.001,0.0088],"p50_ms":12,"p95_ms":480,"by_class":{…}}` |
| `GET` | `/v1/decisions?limit=50` | console backfill, `evidence_png` projected out |
| `OPTIONS` | any | `204` + CORS headers below |

CORS on every response:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: POST, GET, OPTIONS
Access-Control-Allow-Headers: Content-Type
Access-Control-Allow-Private-Network: true
Access-Control-Max-Age: 600
```

Client uses `credentials: 'omit'`.

---

## WebSocket console — `ws://127.0.0.1:8787/v1/stream`

Server→client only. Client sends at most `{"type":"hello","since":"<resume_token>"}` first.
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

---

## Ports — who owns what

| Port | Service | Owner | B and C access |
|---|---|---|---|
| `8787` | `inspect-svc` gateway (the only port the extension ever sees) | A | HTTP only |
| `8000` | vLLM `airlock-text` — Qwen3.6-35B-A3B-NVFP4 | **A** | HTTP only |
| `8001` | vLLM `airlock-vision` — Holo1.5-7B | **A** | HTTP only |
| `8002` | vLLM `airlock-clf` — *conditional, only if NFR-L3 misses* | **A** | HTTP only |
| `27017` | `airlock-mongo` | **C** | direct |
| `5173` | `web/replica` static page | **B** | direct |

**NFR-S1 — only A starts, stops or restarts a GPU process.** B and C never run
`docker run --gpus`, never `vllm serve`, never a bare `python` importing torch with CUDA.
`https://inference.local` is the *sandbox-side* name only — **never put it in the extension.**
