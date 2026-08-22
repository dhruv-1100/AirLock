# RUNBOOK-A — A's demo card

**Owner: A (Vraj, Inference).** Companion to `submission/PITCH.md` (C's script, C narrates)
and `RUN-DAY.md` (C's run sequence). This is only the part A does.

**A's stage job is the terminal.** Two speaking moments, one physical action, and the
close. B drives every click; C narrates everything else. **Do not touch the browser.**

---

## Pre-stage, 16:30 — six checks, ten minutes

Run in this order. Each has a pass criterion; none is optional.

```bash
bash stack/warm.sh
```
**PASS:** both `/health` answer and the warm calls return. Re-warming at demo freeze is
mandatory — a cold first paste on stage is a lost demo (25–57 s of torch.compile).

```bash
grep MemAvailable /proc/meminfo
```
**PASS:** ≥ 8 GB. Below that, NFR-S13 fires and you stop `airlock-vision` **now**, not at
20:00.

```bash
nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv
```
**PASS:** exactly two processes — text and vision. A third means someone launched
something; find it before the demo, not during.

```bash
curl -s localhost:8787/healthz | python3 -m json.tool
```
**PASS:** `clf:true, vlm:true, mongo:true`. Any false → fix before rehearsing.

**PASS:** whiteboard reads **0.68** (text 0.40 + vision 0.28). Ceiling 0.85.

**Terminal layout, pre-staged and never moved after this point:**
- **Left:** `stack/proof.sh` output, scrolled to the memory block.
- **Right:** the sandbox `curl`, typed but **not** executed.
- Font size up. Dark theme. Nothing else on screen — no editor, no logs.

**Type both commands now and leave them at the prompt.** Never type on stage.

---

## 3:00–3:25 · `policy_denied` — A's first moment

Right pane, already typed. Press Enter on C's cue.

```bash
# pre-typed, executed on stage
curl -s https://api.openai.com/v1/chat/completions -H 'Content-Type: application/json' -d '{}'
```

**Expected on screen:** `{"error":"policy_denied","rule":"...","endpoint":"..."}`

**Your line, if C hands you the narration:**

> That's the sandbox layer denying it — deny-by-default egress, five allowlisted
> endpoints. Byte for byte the same JSON the browser rendered. Two layers, one denial
> shape.

**If it returns anything else:** say *"the sandbox is refusing it a different way"*, move
on, and do not debug on stage. C's screenshot from 11:15 is the backup.

---

## 3:10 · The unplug — A's physical action

**B switches to `localhost:5173` FIRST. Confirm you can see it before you touch the
cable.**

> **NEVER unplug while the `chatgpt.com` tab is focused (R15).** One accidental reload
> offline and that tab is gone for the rest of the demo.

Unplug. B pastes the customer list → still blocks. `free -h` and both `/v1/models` are
already visible on your left pane.

**Plug the cable back in immediately afterwards, before anything else happens.**

---

## 4:20–5:00 · The box — A's close

Left pane:

```bash
bash stack/proof.sh
```

**What you are pointing at, in order:** `Memory-Usage: Not Supported` (not a bug — there
is no VRAM), both model processes resident, then `MemAvailable`.

> **Say "Not Supported" is expected before anyone asks.** A judge who spots it first and
> thinks it is an error has already decided the demo is broken.

**Numbers to state — fill from your own runs, never invent:**

| Slot | Source | Value |
|---|---|---|
| memory free | `proof.sh` MemAvailable | `[____]` GB |
| seats/box | `bench/seats.py` | `[____]`, bound by `[vision/text]` |
| vision p50 / p95 | `bench/vision_gate.py` | `[____]` / `[____]` ms |
| summed utilisation | whiteboard | **0.68** of a 0.85 ceiling |

---

## Corrections C must make before this is said aloud

`submission/PITCH.md` still describes the **pre-swap** hardware. Both are spoken lines:

- *"the seven-billion-parameter vision model"* → it is **Nemotron-3-Nano-Omni 30B A3B**.
- *"We're at sixty-four percent"* → the committed total is **sixty-eight percent** (0.68).
- The text model is **Nemotron-3.5-Lightning-30B-A3B-NVFP4**, not Qwen3.6-35B.

A judge from NVIDIA or Dell will know these model names. Getting them wrong on stage
costs more than the sentence is worth.

---

## Q&A — the questions that come to A

**"Why not just block chatgpt.com at the firewall?"**
> A ban and Airlock block the same paste. The difference is the next ten seconds: under a
> ban the employee picks up their phone, and you have lost both the data and the audit
> trail. Here they click "answer locally," get their answer, and nothing left the box. We
> also ship the ban — it is our bottom layer, not our control.

**"Isn't this just a binary classifier?"**
> At its core, yes: a gate with an unusually honest evidence trail. The model must quote
> the exact characters that make a payload sensitive or it gets overruled — that is the
> override rate we report. We spent the day making the gate measurable rather than making
> the ML impressive, because a DLP product lives or dies on its false-positive rate.

**"Why does this need 128 GB?"**
> Three models co-resident: a classifier for the ambiguous fraction, a vision model for
> pasted screenshots, and a 30B that answers the blocked question locally so the control
> does not cost the employee anything. On a 24 GB discrete GPU they do not fit next to
> each other and you swap over PCIe between every paste.

**"What is your false-positive rate?"**
> `[____]` on 1000 benign items, Wilson 95% CI `[____]`. Every false positive was
> hand-adjudicated. If it is 0: *"below 0.3% by the rule of three"* — **never say "zero."**

**"How fast?"**
> p50 `[____]` ms blended. About 86% of pastes never reach a model at all — the block card
> shows the cascade, and you can see which stages ran.

**"Does anything leave the machine?"**
> No, and we do not just assert it: deny-by-default egress with five allowlisted
> endpoints, and we pulled the cable during the demo.

**Anything about the UI, the extension, or the corpus → hand to B or C.** Do not answer
outside inference; a confident wrong answer about someone else's layer is how a demo
loses credibility.

---

## If something breaks mid-demo

| Symptom | Say | Do |
|---|---|---|
| Everything blocks `airlock_unavailable` | *"That's the fail-closed path — it denies by default when the inspector is unsure."* | Nothing on stage. It is the designed behaviour and it reads as intentional. |
| A paste hangs | *"2.5-second budget, then it fails closed."* | Wait it out. Do not touch the terminal. |
| Vision beat fails | — | C cuts to the screenshot. Do not retry live. |
| Host feels wedged | **"FREEZE"** out loud | `nvidia-smi --query-compute-apps=...`, `grep MemAvailable /proc/meminfo`. Under 8 GB → stop vision. Nobody touches anything for 60 s. |

**The one rule on stage: never debug in front of judges.** A fail-closed block screen is a
feature. A person typing commands into a terminal at 2:40 is a broken demo.
