# PITCH.md — C narrates. 5:00 total.

**B drives the browser. C narrates. A drives the terminal and says nothing unless asked a
direct technical question.** Every payload is pre-staged in a scratch file on screen 2.
**Nobody types on stage.**

Read this aloud over B's clicks in all three dress runs (Phase 4). Cut any sentence that
does not land. Write the running clock in the margin as you go.

Bracketed `[X]` values are filled from `results/fpr_report.json` at 16:00 — **not from
memory, and not from the deck if the deck disagrees with the JSON.**

---

## 0:00–0:35 · The problem
*Nothing on screen but the composer.*

> Every one of your employees has a browser tab open to a model you don't run. The data
> that leaves through that tab doesn't leave through your firewall — it leaves through a
> paste. Airlock is a bouncer that sits on the paste.

*(If you are running long, this is the only section you may shorten. Never shorten §7.)*

---

## 0:35–1:10 · Beat 1 — customer list → BLOCKED

**B:** pastes the 12-row `name,email,phone,plan,mrr` block into the ChatGPT composer.

**On screen:** the text never appears. Scanning chip instantly. Block card: `CUSTOMER_RECORD`,
the offending row **underlined**, `bytes egressed: 0`, latency in ms.

> That never left the laptop. And notice what the block says — it quotes the exact
> characters that caused it, and we verified that string is literally present in the
> payload before we blocked. A filter could have caught that one.

**Recovery — card doesn't render but console logs a BLOCK:**
> "The overlay is showing us the verdict in the console instead —" *(point at the log line)*

**Recovery — nothing happens at all:** B pastes the same payload on `localhost:5173`.
One tab switch, three seconds. Do not narrate the switch.

---

## 1:10–1:25 · Beat 2 — benign question → sails through

**B:** pastes *"how do I reverse a linked list in Python?"*

**On screen:** appears normally. No overlay. One `ALLOW` line in the console at
single-digit milliseconds, `tier: T1`.

> No friction. That's the whole game — a control nobody turns off. That one was decided
> in under a millisecond and never touched a model.

**Recovery — it blocks:**
> "And there's a false positive. Let me show you exactly how often that happens."

Then go **straight to §7**. A false positive on stage is survivable **if and only if you
have the denominator.** That is the entire argument for the artifact.

---

## 1:25–2:05 · Beat 3 — unreleased revenue chart → BLOCKED

**B:** pastes `fy26_forecast.png`.

**On screen:** chip reads "inspecting image locally". Block card: `FINANCIAL_NONPUBLIC`,
reason quoting the transcribed title *"FY26 Revenue Forecast"* and the footer
*"Internal — Do Not Distribute"*.

> No regex catches a picture. That's a seven-billion-parameter vision model reading the
> chart's title and footer on this box, in [X] milliseconds.
>
> And notice it didn't try to read the bars. We deliberately never ask it to read data
> values off a chart, because that's the thing these models are worst at. We ask it to
> read the chrome — the title, the footer, the watermark — because that's what actually
> determines whether a slide is confidential.

**Recovery — it times out:** the fail-closed BLOCK screen renders instead.
> "And there's the fail-closed path. When the inspector can't reach a verdict, nothing
> leaves. Deny by default is the product, so it's also the failure mode."

**This failure is on-message. Do not apologise for it.**

If the pre-recorded fallback is in play, B plays the 15-second clip and you say it is a
recording, in those words, before it starts.

---

## 2:05–2:35 · The sanctioned path

**B:** clicks **"Answer this on the local model instead."**

**On screen:** tokens stream into the overlay from the 35B on the box.

> Blocking alone just pushes people to their phones. So the same question gets answered —
> by a thirty-five-billion-parameter model running eighteen inches away. Nothing about
> that round trip left the room.

**Recovery — stream stalls:** B closes the panel.
> "That's the local 35B, and you'll see it live in the terminal in ten seconds."

Hand to A's `proof.sh`, which shows both `/v1/models` responding.

---

## 2:35–3:00 · Beat 4 — the detector learns
### ← **Cut this first if running long.**

**B:** on a fresh block card, clicks **"Mark benign."** Re-pastes the same payload → it
sails through. Then pastes a *near neighbour* → it still blocks.

> An analyst just corrected it. The payload and its embedding went back into the corpus
> in MongoDB, and the next paste of that shape passes — while a neighbour still blocks.
> The detector learned without retraining a model. You cannot do that with a regex.

---

## 3:00–3:25 · `policy_denied` and the unplug

**A:** runs the pre-staged `curl` from inside the sandbox. Raw
`{"error":"policy_denied","rule":...,"endpoint":...}` on screen.

> That's the sandbox layer — deny-by-default egress, five allowlisted endpoints, GitHub
> blocked. Byte for byte the same JSON the browser renders. Two layers, one denial shape.

**B:** switches to `localhost:5173`. **A unplugs the ethernet.** B pastes the customer
list again → still blocked. `free -h` and both `/v1/models` visible on A's terminal.

> Cable's out. Still blocking, still answering. There is no cloud in this system.

**The cable goes back in immediately afterwards, before anything else.**

> **NEVER unplug while the `chatgpt.com` tab is focused (R15).** One accidental reload
> offline and that tab is gone for the rest of the demo.

---

## 3:25–4:20 · The number
### ← **Never cut this. This is why the pitch exists.**

**B:** scrolls the console — hundreds of ALLOW lines — then opens the report panel.

> Three pastes is a demo. Here's the detector.
>
> We measured a **[X]%** false-positive rate, ninety-five percent confidence interval
> **[a, b]**, over **one thousand benign pastes we did not write** — four hundred real
> ChatGPT prompts from WildChat, two hundred Stack Exchange questions, a hundred and
> eighty code problems from MBPP and HumanEval, a hundred and twenty consumer-finance
> complaints, and a hundred Wikipedia paragraphs.
>
> The published industry average for DLP false positives is fifty-one percent.

**B:** drags the threshold slider 0.55 → 0.30. FPR and recall move live.

> Every DLP product has this dial. The difference is where it lives. On a cloud DLP you
> file a ticket and wait a quarter, and you never see the curve. Here the curve is on
> your desk — because the corpus and the inference are both on the box.

**Recovery — slider misbehaves:** read the three-row table off the deck.
**The number is the asset; the slider is the flourish.**

### If asked "is your sensitive set synthetic?" — deliver this verbatim:

> Our sensitive set is synthetic, so recall is an upper bound. Our benign set is
> human-written, so **FPR is the number we stand behind.**

### If asked "how do you know those aren't just easy negatives?"

> Thirty-six of them are hard negatives we wrote to break it — published Stripe test
> cards, `AKIAIOSFODNN7EXAMPLE`, placeholder keys, git SHAs, a 10-Q excerpt, and questions
> *about* credit-card regexes that contain no card. That bucket is reported as its own
> line, not folded into the total.

---

## 4:20–5:00 · The box, and the close

**A:** `stack/proof.sh` on screen.

> `nvidia-smi` won't show you a VRAM bar on this machine. That's not a bug — there is no
> VRAM. The thirty-five-billion-parameter text model and the seven-billion-parameter
> vision model are both resident, right now, in the same hundred and twenty-eight
> gigabytes the operating system is running in.
>
> On a twenty-four-gigabyte discrete GPU neither fits next to the other, and you'd be
> swapping over PCIe between every paste. Here there is no PCIe to swap across.
>
> NVIDIA's own reference recipe for this exact text model runs at forty percent memory
> utilisation. We're at sixty-four percent with two models and **[Y]** gigabytes still free.
>
> At the measured throughput that's **[Z] seats per box**, bound by the vision path, at a
> hundred and sixty watts — about three hundred and fifty euros a year of electricity for
> the whole fleet.
>
> That's how you get to Dell's eighty-seven percent number: you stop paying per token, and
> you stop paying the interruption tax.

---

# Anticipated questions

**"Why not just block the sites?"**
> Then people use their phones, and you've lost both the data and the visibility. Airlock
> answers the question locally, which is the only version of this control that survives
> contact with employees.

**"What about screenshots, or photographing the screen?"**
> Out of scope, and we say so in the submission. We intercept the clipboard payload. A
> camera pointed at a monitor is a different threat model and we don't claim it.

**"Does the agent see the confidential data?"**
> No. The agent gets the verdict record and the question with the confidential spans
> already removed. It has no network tools and it cannot request the original payload.

**"How do we know nothing was called remotely?"**
> We don't ask you to take our word for it. Every inference call emits an OCSF record
> naming its provider URL. `evidence/rule02-providers.txt` is a `jq` over the full run:
> one provider, `host.openshell.internal`, zero cloud hosts. And the egress denial is
> enforced at the proxy, outside the sandbox, where the agent cannot reach it.

**"What's your worst class?"**
> *(Name it from the by-class table without hesitating.)* Publishing the weak one is what
> makes the strong ones believable.

**"What would you do with another day?"**
> Calibrate the image path properly — the image FPR has a much smaller denominator than
> the text one, and we report them separately rather than averaging them into something
> flattering.

---

# Timing discipline (Phase 4)

| Beat | Budget | Cumulative |
|---|---|---|
| Problem | 0:35 | 0:35 |
| Beat 1 — customer list | 0:35 | 1:10 |
| Beat 2 — benign | 0:15 | 1:25 |
| Beat 3 — image | 0:40 | 2:05 |
| Sanctioned path | 0:30 | 2:35 |
| Beat 4 — learns | 0:25 | 3:00 |
| `policy_denied` + unplug | 0:25 | 3:25 |
| **The number** | **0:55** | **4:20** |
| The box + close | 0:40 | 5:00 |

**Cut order if over at the dress run (R17):** beat 4 first, then the sanctioned path.
**Never the number.**

Dress run over 4:45 → cut immediately, do not "try to talk faster".
