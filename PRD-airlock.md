# PRD — Airlock

**Dell x NVIDIA Hackathon · Aug 22 2026 · Local AI on Dell Pro Max with GB10**

> A bouncer on the machine. At the moment something is about to leave, it looks at the screen the way a person would and stops it if it shouldn't go — then answers the same question locally so the employee has no reason to smuggle.

---

## 1. Summary

| | |
|---|---|
| **Deliverable** | Browser extension + local agent that intercepts paste / file-upload / form-submit, returns allow-or-block with a reason, and re-routes blocked questions to the on-box model |
| **Buyer** | CISO or IT director at any company with employees and laptops |
| **Always-on trigger** | The interceptor is resident and running; OpenClaw heartbeat sweeps the verdict log for pattern shifts |
| **Hero model** | Nemotron 3 Nano Omni 30B-A3B NVFP4 (reads the screen) |
| **Primary risk** | Omni has never been served on sm_121. **Binary gate at 10:15.** |

**Judge panel scoring:** 32.7/40 · 1 of 3 yes · 6 s to legibility (best in field) · feasibility 6/10. Local-first scored **9, 10, 10** — the strongest local argument of any candidate. Technical execution scored **5, 6, 7** — the weakest.

**This is a pitch with a product problem, not a product with a pitch problem.** At a five-minute pitch weighted 30% on demonstration, that is the better problem to have — but only if §9 gets built.

---

## 2. Problem

81% of employees use AI tools nobody approved; 33% admit pasting company data into them. Samsung allowed ChatGPT and within twenty days three engineers had pasted chip source code into it. Apple, JPMorgan, Goldman, Citi, Bank of America, Verizon and Amazon all did the same blunt thing.

Bans don't work. 66% of office professionals admit using AI tools they believed weren't permitted; 57% hide it from their supervisor. 82% of enterprise GenAI usage comes from unmanaged personal accounts with zero visibility. AI has overtaken SaaS as the number-one data exfiltration channel.

IBM's 2025 breach report puts shadow AI in 20% of breaches, adding up to **$670,000** to an average **$4.44M** incident — and **97%** of organisations that suffered an AI-related breach had **no AI access controls at all**.

The precedent isn't hypothetical: **DHS cut off commercial ChatGPT and Claude for ~20,000 headquarters staff in May 2025 and stood up an internal one instead.** That is the exact shape of this product.

---

## 3. Why local — and the correction you must make

**The argument that scored 9/10/10:**

> To find out whether something is confidential, you have to look at it. So a cloud service that inspects every screen in your company is the exact leak you were trying to prevent, wearing a different logo.

It's a logical paradox, not a preference. It needs no statute, no acronym, no explanation.

### ⚠️ But do not state it unqualified

Cloud content inspection is a large, thriving business: **Cyera $12B (June 2026), Netskope $7.3B at IPO on $707M ARR, Island $4.8B.** If the paradox were airtight, Cyera would not be worth twelve billion dollars. A judge who follows security funding knows those names, and an overstated claim collapses under one question.

**Narrow it instead:**

> "File-scanning DLP in the cloud is a real business — Cyera's worth $12B. But those products inspect *files in transit*. We inspect *your screen* — every chart, every whiteboard, every Slack thread you happen to have open. Nobody signs a contract that streams that to a vendor. The category exists in the cloud; this specific capability can't."

That survives contact. Name two competitors out loud before a judge does.

---

## 4. What it does

A bouncer on the machine. At the moment something is about to leave — a paste into a chat box, a file upload, a form submit — it looks at the target region the way a person would, and stops it if it shouldn't go.

**Then it re-routes the same question to the local model on the box, so the employee still gets their answer and has no reason to smuggle.**

That last part is the design insight. **A security tool everyone routes around is worse than no tool.** Most security demos show you a wall; this one shows a wall and a door.

---

## 5. Architecture

```
Employee laptop
  │  browser extension + small local agent
  │  intercepts: paste · file-upload · form-submit
  │  captures the target region only ──────────────┐
  │                                                │
  │  ◀── verdict (allow / block + reason) ──────┐  │
  ▼                                             │  ▼
[block overlay]                          GB10 box (shared)
                                          ├─ Nano Omni 30B-A3B NVFP4 (20.9 GB) — reads the screen
                                          ├─ Lightning 30B-A3B NVFP4 (20.1 GB) — sanctioned answer path
                                          ├─ MongoDB atlas-local — verdict log + console
                                          └─ OpenShell — deny-by-default egress
```

**Both models permanently resident: 41 GB of ~110 GB usable.** That matters — *a vision model paged in on demand cannot sit in the path of a keystroke.*

### Model substitutions from the original spec

| Spec called for | Using | Why it's an upgrade |
|---|---|---|
| Holo1.5-7B | **Nano Omni 30B-A3B NVFP4** | Native GUI-screenshot understanding — OSWorld 47.4%, OCRBenchV2 67.04. Already on the drive. |
| Qwen3.6-35B | **Lightning 30B-A3B NVFP4** | NVIDIA's claim: ~30% faster than Qwen3.6 35B at equal accuracy, purpose-built for the OpenClaw harness the rules mandate. |

Say both out loud. *"We're running NVIDIA's own models, released this month, on NVIDIA's box"* is a better line in front of these judges than naming a third-party VLM.

### ⚠️ Critical implementation constraint — decided at 10:00, not found at 16:00

**The client owns the interception.** Nothing touches `xdotool`, `pyautogui`, or any synthetic input. On DGX OS 7's Wayland default those **silently return exit code 0 while doing nothing** — it looks like it works right up until you're on stage.

---

## 6. Required stack

**OpenClaw**
- The local agent is an OpenClaw client; the **sanctioned answer path** is an OpenClaw session against Lightning
- `HEARTBEAT.md` (non-empty scratch section) sweeps the verdict log and surfaces shifts — *"three people tried to paste from the pricing deck this hour"*
- `ask_user` gates the only irreversible action: adding a permanent allow-rule for a pattern
- `sessions_spawn` for parallel verdicts when a batch of files is uploaded at once

**NemoClaw**
- `nemoclaw launch airlock` — sandbox with GPU passthrough, both models served
- `nemoclaw airlock inference set` — switch the vision tier live without editing config (a good 15-second beat)
- `nemoclaw airlock snapshot create pre-demo` — the on-stage undo

**OpenShell**
- Network **default-deny**. The demo beat: the agent attempts an outside classification endpoint, `{"error":"policy_denied"}` lands raw and full-screen.
- `filesystem_policy` confines captured regions to a quarantine path nothing else can read — **images never leave the machine**, and OpenShell enforces it rather than you promising it
- **Enumerate every host path before the first `nemoclaw onboard`** — filesystem and process policy are LOCKED at sandbox creation
- `openshell policy set` **replaces the whole document** — write one merged `policy.yaml`

**MongoDB — REQUIRED STACK, not a bonus.** Absent MongoDB is a compliance failure. Stand it up at **10:15 alongside Gate 1**, not at 13:00.

```
verdicts   {ts, action, rule, reason, latency_ms, surface, embedding:[768]}
patterns   {pattern_id, label, embedding:[768], hits, first_seen}
telemetry  time-series: {ts, p50_ms, p95_ms, allow_rate}
```

Four things doing real work:

1. **Change stream on `verdicts` drives the live console** — allows and blocks appear as they happen, which is also what makes it always-on rather than a request/response service.
2. **`$vectorSearch` over blocked-content embeddings** → *"this is the fourth person this week trying to send the same roadmap slide."* That is a genuinely better product, not just a demo beat — it turns single verdicts into a pattern.
3. **Time-series collection** for the latency distribution on your numbers slide — p50/p95 straight out of a `$setWindowFields` aggregation rather than a spreadsheet.
4. **The FP-rate table in §9 is an aggregation pipeline**, computed in Mongo against the benign corpus. The evidence a judge asked for is produced by the database.

A KV store gives you no ANN, no change stream, no window functions. Say exactly that.

**Setup gotchas:** `?directConnection=true`, `hostname:` set, **three** volumes (`db`, `configdb`, **`mongot`**). Tag 8.3, not 8.0. **Never `autoEmbed`** — it calls Voyage AI over HTTPS, and for *this* project in particular that is fatal: your entire pitch is that nothing leaves the machine.

**Schema diagram in the README.**

---

## 7. Demo — the best 30 seconds in the candidate set

A laptop screen mirrored on the projector. Nothing else.

**Beat 1.** User opens ChatGPT, pastes a customer list. Before the cursor lands, a red curtain drops: **BLOCKED — 47 customer records.**
> *"Fine. A filter could have caught that."*

**Beat 2.** Second paste: a plain Python question. Sails straight through. No popup, no friction.
> *"A security tool everyone routes around is worse than no tool."*

**Beat 3 — the one that wins the room.** A screenshot of an unreleased revenue chart. An image. No text at all. Red curtain: **BLOCKED — appears to be an internal financial forecast.**

Everyone simultaneously understands that the machine *looked at a picture and knew what it was.* No regex on earth catches that. **The leak that ends careers isn't a card number — it's a photo of a whiteboard or a slide from the roadmap deck.**

**Beat 4.** The blocked question gets answered by the local model. The door, not just the wall.

**Beat 5.** `{"error":"policy_denied"}` raw on screen. Then the cable comes out and the fourth paste is still blocked.

---

## 8. Why this box — and the number you must not overclaim

Two models co-resident, no loader latency in the keystroke path.

**Be honest about the throughput regime.** Vision is prefill-bound, so the concurrency multiplier here is **1.5–2.5×, not 120×.** Say that number out loud before a sponsor engineer catches you borrowing the text figure.

**The number you do claim is seats per box, measured on the day.** Because you only look at the moment of egress rather than continuously, volume is roughly **200× lower** than the naive design.

**The cost inversion:** a vision agent burns ~45× the tokens of a text agent — roughly **$115 per person per day** at list API pricing for continuous screen watching, forever, per seat. The box is **$6,300 once.**

---

## 9. 🔴 The thing that decides yes or no

All three judges converged on the same gap, and the one who said yes conditioned it explicitly:

> *"Yes — makes top 3 on the strongest local-first argument in the field and the fastest-landing demo, **provided they arrive with a false-positive denominator** rather than a single volunteered anecdote."*

> *"Three pastes is a demo, not a detector. What is your false-positive rate over a thousand benign pastes, measured on a corpus somebody other than you wrote? A DLP tool that blocks 3% of a developer's clipboard is uninstalled inside a week, and you have shown me the numerator with no denominator anywhere."*

### Requirement

**A benign corpus of 500–1,000 real developer/office pastes, and a measured false-positive rate.**

Sources somebody else wrote: public GitHub code snippets, Stack Overflow answers, public documentation, open-licensed business documents. **Not written by you.** State the provenance on the slide.

**Report:** FP rate over the benign corpus · TP rate over a seeded sensitive set · latency p50/p95 · the confusion matrix.

**This single artifact is what converts a 1/3 into a 3/3.** It is also, precisely, the thing that gets cut at 15:00 when the overlay animation isn't working. **Schedule it before the UI and treat it as untouchable.**

You almost never get told the exact artifact that flips a vote. You have been.

---

## 10. Build plan — 3 people, 10:00–18:00

**A** = models/inference · **B** = corpus + eval + policy + Mongo · **C** = client/extension/UI

| Time | A | B | C |
|---|---|---|---|
| 10:00–10:15 | **🚦 GATE 1 (BINARY): does vLLM 26.03 serve Nano Omni at all?** Not latency — existence. | | |
| 10:15–10:45 | **🚦 GATE 2:** median verdict time on 20 real 1280×720 screenshots | atlas-local up; `verdicts` schema; **benign corpus assembly starts** | Extension skeleton: paste/upload/submit interception, **client-side only, no synthetic input** |
| 10:45–12:00 | Omni verdict endpoint, guided JSON | benign corpus ≥500 assembled with provenance recorded | block overlay + allow path, 120pt legible |
| 12:00 | **🚦 SKELETON GATE** — one paste in, one verdict out, overlay renders | | |
| 12:00–13:30 | Lightning sanctioned-answer path | `policy.yaml` merged, `audit` mode; change stream → console | the three demo pastes wired and rehearsed |
| 13:30–15:00 | latency tuning per Gate 2 branch | **FP rate measured over the benign corpus; confusion matrix** | `$vectorSearch` "fourth person this week" beat |
| 15:00–16:00 | seats-per-box measured | OpenShell → `enforce`; policy_denied beat | cable pull rehearsed; numbers slide |
| **16:00–16:30** | **🧊 FREEZE.** Snapshot. Capture the run for one-keystroke replay. | | |
| 16:30–18:00 | **All three: written submission.** | | |

### Gate 2 branches — the pitch does not change a word in any of them

| Median verdict time | Action |
|---|---|
| **< 1.5 s** | Proceed as designed |
| **1.5–4 s** | Moment-of-egress only — **which is the better design anyway** |
| **> 4 s** | Downscale to 896px, or two-stage: cheap classifier gates, VLM confirms |

**Stubbed and disclosed:** one browser, one OS, one machine. No MDM, no fleet enrolment, no policy console. **You are building 10% of the product — say what you built and what you didn't.**

---

## 11. Risks

| Risk | Severity | Gate | Handling |
|---|---|---|---|
| **vLLM won't serve Omni** | **Highest** | **10:15** | Binary. If no model class exists, no latency tuning fixes it. Fallback: Omni via transformers outside vLLM (slower, fiddlier), or **abandon → pivot to CARRY THE ONE**, which runs on Lightning alone. Know by 11:00. |
| VLM latency unmeasured on sm_121 | Highest | 10:45 | Three branches above. |
| Threat model has holes | High | — | *"Save the file, open it on your phone, photograph the screen."* **Unanswerable as a claim to airtightness — so don't claim it.** → *"Every DLP product ever sold has that hole. We're not selling airtight, we're selling friction and a record — same as the twelve-billion-dollar company doing this in the cloud."* Turns the crowded market into your defence. |
| Building 10% of the product | High | — | Say it first. Scope honesty reads as maturity. |
| **The surveillance read** | Medium | — | **Handle in the product, not a slide.** Only egress moments; images never leave the machine; the console shows *allowed* as prominently as *blocked*; the cable pull proves it. **Say this in the first 30 seconds** or a judge spends their whole attention there. |
| Crowded market | Medium | — | Nightfall, Cyberhaven, Netskope, Zscaler, Prompt Security, WitnessAI, LayerX, Island. Name two before a judge does. Use the §3 narrowed claim. |
| Wayland silently no-ops synthetic input | High | 10:00 | Client owns interception. Decided, not discovered. |
| Live demo fails | — | 16:30 | Captured run, one-keystroke replay, **labelled out loud.** |

---

## 12. Pitch

**Headline:** *To find out whether it's confidential, something has to look at it. That something shouldn't be a stranger.*

**Three bullets**
1. 81% of employees use unapproved AI tools; 33% paste company data into them. 82% of enterprise GenAI runs through unmanaged personal accounts.
2. Shadow AI appears in 20% of breaches and adds **$670K** to a **$4.44M** incident — and 97% of breached orgs had **no AI access controls at all**.
3. Continuous cloud screen-inspection is ~**$115/person/day** at list API pricing, forever. The box is **$6,300** once. FP rate **⟨measured⟩** over ⟨n⟩ benign pastes we didn't write.

**Opening 20 seconds:** *"Samsung allowed ChatGPT. Twenty days later three engineers had pasted chip source code into it, and Samsung banned it permanently. Every company in this room has made the same choice — ban it and watch people route around you, or allow it and hope. We built the third option, and it looks at your screen without anyone else ever seeing it."*

**Q&A prep**
- *"What's your false positive rate?"* → §9. **The whole reason you built the corpus.**
- *"Cyera does this in the cloud and is worth $12B."* → §3 narrowed claim.
- *"They'll photograph the screen with a phone."* → Friction and a record, not airtight. Same as every DLP product ever sold.
- *"Isn't this surveillance?"* → Egress moments only, images never leave the machine, and here's the kernel policy that enforces it.
- *"What's the throughput multiplier?"* → 1.5–2.5×, prefill-bound. **Volunteer this.**

---

## 13. Submission — 16:30–18:00

**32 of 40 teams never pitch.** The 18:00 cut is made on the written submission alone.

- [ ] Title + hook + hero screenshot: **the red curtain on the image paste**, not the architecture
- [ ] <3 min video: the three pastes, then the local answer, then the cable pull
- [ ] README: architecture, **MongoDB schema diagram**, run instructions, **FP rate table with corpus provenance**
- [ ] Explicit scope statement — what you built, what you didn't
- [ ] Sponsor stack: one line each for OpenClaw, NemoClaw, OpenShell, MongoDB
- [ ] Written against the **literal headings of the BuilderBase rubric** read at 10:00

---

## 14. Traps

- **OpenClaw memory search defaults to OpenAI embeddings.** Set `memory: { search: { provider: "local" } }` — otherwise your "nothing leaves the machine" demo calls `api.openai.com` on stage. **This one is fatal for this project specifically.**
- **MongoDB `autoEmbed` calls Voyage AI over HTTPS.** Never use it.
- **Ollama fallback: `api: "ollama"` with NO `/v1` suffix.** For vLLM the `/v1` suffix *is* correct.
- No `xdotool`, no `pyautogui`, no synthetic input. Ever.
- `nvidia-smi` shows no memory on this iGPU — read `/proc/meminfo`.
- ~119 GiB visible. `sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'` between loads.
- Airflow. 280 W adapter.

---

## 15. Verify in the first 30 minutes

1. **Does vLLM 26.03 serve Nano Omni?** ← the one that decides everything
2. Does NVFP4 load on aarch64 at all?
3. `nemoclaw host probe` — Dell unit detected as Spark-class?
4. `$vectorSearch` in mongosh against the bundled mongot
5. Can the OpenShell sandbox reach MongoDB? No `mongodb` preset exists; needs a DNS hostname, not an IP literal
6. Read the actual BuilderBase rubric

---

## 16. Verdict against Full Coverage

Airlock has the better opening, the better local argument, and the better single demo beat. Full Coverage has the better product.

**The difference is where the risk sits.** Full Coverage's risk is a known unknown with a clean fallback — if ASR doesn't come up by 11:20, Text Mode ships the identical product over transcripts. Airlock's risk is that its central capability has never been measured on this silicon, and its threat model has holes a security-literate judge opens in one question.

**Build Airlock if** you spend 10:00–10:45 measuring before writing a line of product code, **and** you commit to the benign-paste corpus. Those two things are the entire difference between 1/3 and 3/3.

> **Portfolio note for two teams:** Airlock and PROOF OF LIFE are both Omni-dependent — if Gate 1 fails, both die at the same moment. Put one team on Omni and one on Lightning-only so a single gate can't take out both.
