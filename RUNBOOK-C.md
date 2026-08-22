# RUNBOOK-C — every command C runs, in time order

C owns three different jobs (stack bring-up, data/evaluation, the written submission) and
the submission alone picks the top 8. This file exists so none of it is re-derived under
time pressure.

**Rules that never bend:**
- **NFR-S1 — C never starts a GPU process.** No `docker run --gpus`, no `vllm serve`, no
  bare `python` importing torch. C consumes `:8000`/`:8001`/`:8787` over HTTP only.
  MongoDB has no `--gpus` and is therefore C's to run.
- If the box is in trouble, say **"FREEZE"** out loud and stop touching things for 60s.
- Anything that fails has a pre-declared fallback below. **No gate resolves to "debug it."**

---

## 10:00–10:10 · P0 — the call that unblocks A

```bash
bash stack/up_mongo.sh
```

Handles the container, the health poll, and the mongot heap verification, including the
`JAVA_TOOL_OPTIONS` fallback. It prints **MONGO HEAP VERIFIED** when done.

> **Say "mongo heap verified" out loud. A is blocked until you do.** Target ≤10:08.

If it escalates instead (heap still uncapped, R8): run plain `mongo:8` without mongot and
set `AIRLOCK_RRF=client`. Retrieval then uses the client-side RRF path, which emits an
identical `score`/`scoreDetails` shape — B's UI does not change.

```bash
nemoclaw --version
nemoclaw host probe --json | tee evidence/airlock-host-probe.json
nemoclaw profiles list --json
nemoclaw agents list
```

Then start the corpus — **it has zero dependencies, so it goes first**:

```bash
python bench/build_benign.py --seed 1337          # needs dumps in data/dumps/
```

---

## 10:10–10:35 · P1 — onboard

**Say `text,image` out loud before pressing enter.** Missing it is a 15-minute rebuild.

```bash
NEMOCLAW_NO_EXPRESS=1 NEMOCLAW_INFERENCE_INPUTS=text,image NEMOCLAW_AGENT=openclaw \
NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1 \
nemoclaw onboard --name airlock --no-gpu --events=jsonl | tee evidence/onboard.jsonl
```

While it runs (unattended):

```bash
bash stack/seed.sh          # blocks until both search indexes are READY + queryable
```

> If it prints "indexes not READY", that is R10. **Check `queryable`, not the embeddings.**
> A `$vectorSearch` against a non-queryable index returns empty results, not an error.

---

## 10:35–10:45 · P2 — advisor check

```bash
openshell settings set --global --key policy_advisor_enabled --value true
openshell settings get --key policy_advisor_enabled --show-scope
nemoclaw airlock exec -- curl -sS https://api.openai.com/v1/models
```

**Announce PATH A or PATH B to the room. Do not revisit it.**

---

## 10:45–11:30 · P3 — policy

```bash
nemoclaw airlock exec -- which python3      # real interpreter path, do not guess
nemoclaw airlock exec -- which openclaw

nemoclaw airlock policy add local-inference --dry-run
nemoclaw airlock policy add local-inference --yes

nemoclaw airlock policy add --from-file ./policy/airlock-egress.yaml --dry-run
nemoclaw airlock policy add --from-file ./policy/airlock-egress.yaml --yes

nemoclaw airlock policy list       # capture EXACT baseline rule names into policy/exclusions.md
nemoclaw airlock policy explain --json | tee evidence/airlock-policy.json
openshell settings set --global --key ocsf_json_enabled --value true
```

> An endpoint with no matching `binaries` entry **authorises nothing**. The policy loads
> and then nothing works. This is the most common silent failure in the whole stack.

---

## 11:30–12:00 · P4 — the denial artifact

```bash
nemoclaw airlock exec -- curl -sS https://api.openai.com/v1/models \
  | tee evidence/policy-denied.json
nemoclaw airlock logs --follow          # verify both channels
```

**Screenshot it now. This is demo beat 5 and it is in the bag at 11:15.**

---

## 11:30–12:30 · corpora and retrieval

```bash
wc -l data/benign_v1.jsonl              # must be 1000
python bench/build_sensitive.py --seed 1337
python bench/seed_corpus.py             # nine clauses + ~200 exemplars, CPU embeddings
python tools/fake_decisions.py --burst 200    # gives B a populated console immediately
```

Verify retrieval is actually live before trusting any cited clause:

```bash
mongosh "mongodb://localhost:27017/?directConnection=true" \
  --eval 'db.policy_corpus.aggregate([{$listSearchIndexes:{}}]).toArray()
            .map(i=>({name:i.name,status:i.status,queryable:i.queryable}))'
```

---

## 12:00–13:00 · P5 — middleware gate

```bash
nemoclaw airlock status --json | jq .openshellVersion
```

**13:00 hard decision: Tier A or Tier B. Announce it. Never revisit.**

---

## 13:00–14:30 · P6 — OpenClaw + demo assets

```bash
nemoclaw airlock skill install ./skills/airlock-verdict-explainer/
openclaw skills install xejrax/clipboard
openclaw plugins enable policy
openclaw automations add                      # ledger sweep

python bench/make_images.py --all --seed 1337 # demo chart + 20 gate + 100 benign
```

> Deliver `data/images/demo/fy26_forecast.png` to B **by 13:15**. B is unblocked by any
> 1280×720 PNG in the interim — B is wiring transport, not content.

Exclude the baseline rules **only after** skills are installed (order matters):

```bash
nemoclaw airlock policy exclude <nvidia_api_rule> --dry-run
nemoclaw airlock policy exclude <nvidia_api_rule> --force
nemoclaw airlock policy exclude <npm_rule> --force
```

---

## 13:00 · the harness starts

A runs it, C owns it. **Running by 13:00** (NFR-T5: 1000+400 in ≤15 min).

```bash
python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55
```

If Mongo is not producing documents by 14:30 → **R4 bypass, no discussion:**

```bash
python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55 --no-mongo
```

The JSON files are authoritative either way; the aggregation stays in the writeup as the
production path.

---

## 14:30–16:00 · P7 — the numbers

```bash
python bench/report.py                    # Wilson CI, per-class, per-source, figures
```

Then the two things that cost 40 minutes and buy disproportionate credibility:

1. **Hand-adjudicate every false positive.** `results/false_positives.md` lists each one
   with its span. With FPR <1% that is fewer than ten items. Report verbatim, e.g.
   *"7 blocked; on review 3 contained a genuine live-looking key the corpus author had
   pasted; corrected FP = 4/1000."*
2. **Inter-rater check.** C and whoever is free independently review a random 100 benign
   items. Report n, disagreements, and Cohen's κ.

```bash
bash stack/proof.sh | tee results/proof_$(date +%s).log
python submission/fill.py                 # substitutes every number from fpr_report.json
```

> `fill.py` **refuses** to run while `corpus_is_real` is false. That is deliberate.
> It also lists every hand-filled placeholder with its owner — work that list to zero.

---

## 16:00 · G4 — feature freeze (C owns this gate)

Pass requires `results/fpr_report.json` on disk with `n ≥ 1000`, an integer `false_pos`,
an `fpr`, a Wilson `ci95`, and a `by_class` breakdown. Plus the ablation table and the
vision sweep table.

**From this moment no code changes and nothing large is loaded on the host** — feature
freeze is also an allocation freeze (NFR-S11).

---

## 16:00–16:30 · P8 — dress runs

Read `submission/PITCH.md` aloud over B's clicks, all three runs. Cut any sentence that
does not land. Write the running clock in the margin.

- Freeze the deck. **Every number on it must match `fpr_report.json` exactly.**
- **Any VRAM bar on any slide is deleted on sight (R16).**
- Unplug the ethernet once and plug it back in. Do not discover a DHCP problem at 20:04.

---

## 16:30–17:45 · P9/P10 — evidence and submit

```bash
sudo cp /var/log/openshell-ocsf.$(date +%F).log evidence/
jq -r 'select(.class_uid==6003) | .ai_model.ai_provider' \
  evidence/openshell-ocsf.$(date +%F).log | sort | uniq -c \
  | tee evidence/rule02-providers.txt
openclaw policy check --json --severity-min error | tee evidence/openclaw-policy-check.json
nemoclaw airlock policy explain --json | tee evidence/airlock-policy.json
```

**`evidence/rule02-providers.txt` is the single strongest artifact in the submission.**
Expect one provider, `host.openshell.internal`, and zero cloud LLM hosts.

### Final read, 17:30 — three checks

1. Does the first screen contain the FPR **with its denominator**? If not, move it up.
2. Does any number in the prose disagree with `fpr_report.json`?
   *(`fill.py` makes this vacuous — but grep anyway.)*
3. Is there a claim anywhere that was not measured? Delete it, or mark it explicitly as
   derived arithmetic pending measurement.

```bash
grep -n '{{' submission/SUBMISSION.final.md    # MUST return nothing
```

**Submit by 17:45. Not 17:55.** Then say "SUBMITTED" out loud.

---

## Fallback quick reference

| Symptom | First thing to check | Fallback |
|---|---|---|
| mongot heap > 4 GB | `docker exec airlock-mongo grep -i heap /tmp/mongot.log` | `JAVA_TOOL_OPTIONS`, then plain `mongo:8` + `AIRLOCK_RRF=client` |
| Retrieval returns nothing | `queryable`, **not** the embeddings | `AIRLOCK_RRF=client`, or the static `policy.yaml` enum |
| Console stops after a re-seed | did the `invalidate → startAfter` transition fire? | it is in `stream.py`; check before suspecting the socket |
| Console never updates at all | **is `websockets` installed, and was uvicorn restarted after?** | `pip install websockets` then restart — see INTEGRATION.md §7 |
| `mongosh` hangs | `directConnection=true` missing from the URI | add it |
| Harness not producing docs | — | `--no-mongo`, compute from the JSON |
| `/v1/decisions` 404s | is `console_api` mounted in `app.py`? | INTEGRATION.md §1 |
| Everything looks fine but nothing persists | `/healthz` reports `mongo` from an import, not a ping | INTEGRATION.md §6 |
