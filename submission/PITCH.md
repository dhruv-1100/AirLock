# PITCH.md — narration for the recorded demo

**The GB10 is no longer available, so there is no live demo.** This is narration for
B's 121-second screen recording of the real system (`submission/airlock-demo.md` lists
what is in each second). If only the earlier 62-second cut can be found, the same lines
apply in a different order — it is recoverable with
`git show 0878291:submission/airlock-demo.mp4 > airlock-demo.mp4`.

Rewritten 2026-10-13. The earlier script described a live demo of the *planned* system —
a 35B and a 7B model, an image beat that blocks, a cable unplugged on stage, a moving
threshold slider and a 51% industry comparison. None of those survive measurement. Every
claim below has a source in `results/` or `evidence/`.

---

## Before it plays — 20 seconds

> Every employee has a browser tab open to a model the company does not run, and company
> data leaves through it as a paste — not through the firewall. Airlock sits on the paste.
> It inspects it on the laptop's own hardware, blocks it if it is confidential, and still
> answers the question locally so nobody is pushed onto their phone.

## Over the recording

**~20–50 s — customer list, blocked.**
> A twelve-row customer list. It never reaches the page. The card quotes the exact row
> that caused the block, and that text was checked to be literally present in the paste
> before we blocked — if the model can't point at it, we don't block. This decision took a
> 30-billion-parameter model about three seconds, on the box. Nothing left it.

**~50–58 s — the score breakdown.**
> This is why it ranked the way it did: MongoDB fusing a semantic search and a keyword
> search over our policy examples, with each one's contribution shown. The policy clause it
> cites is chosen from that retrieval, so it can't invent one.

**~58–80 s — answered locally.**
> Blocking alone pushes people to workarounds. So the same question is answered by the
> same 30B model, on the same machine.

**~80–90 s — a benign question goes through.**
> An ordinary question goes straight into the chat box. That's most pastes.

**~90–100 s — the same list again.**
> Pasted twice: blocked in about a millisecond from MongoDB's record of the first decision.
> No model call.

**~100–115 s — the console.**
> Every decision streaming live off a MongoDB change stream.
>
> *If the on-screen recall is noticed: "That recording shows 87.8%. It's wrong — our tooling
> counted fifty test cases that should be allowed as if they should be blocked. The correct
> figure is 98.5%, and the error made us look worse, not better."*

**~115–121 s — the sandbox evidence.**
> Inside the agent sandbox, the four big cloud model APIs return "policy denied" at a proxy
> the sandbox can't touch, and every inference request in the log went to one place: the
> local model.

## After it ends — the number, 40 seconds

> Three pastes is a demo. Here's the measurement. We ran a thousand real, human-written
> pastes we didn't write — chat prompts, Stack Exchange questions, code problems, consumer
> complaints, encyclopedia text. Airlock wrongly blocked **4.0%** of them, confidence interval
> roughly three to five and a half percent. On the code and technical text engineers paste
> most — four hundred and eighty items — it wrongly blocked **none**.
>
> Most of the errors came from one source: consumer complaints where personal details had
> already been redacted to strings of X's, which the model mistook for card numbers. That's
> the clearest thing to fix next.

**Do not say** "N times better than the industry average." The figure usually quoted —
51% — is the share of *alerts* that are wrong, which is a different measurement from ours.
On a like-for-like basis our alerts land in the same range, depending on how often pastes
are truly sensitive (`SUBMISSION.md` §2).

---

## Questions, and the answer to give

**"Where does the 4% come from — can I check it?"**
> The corpus, the harness and every per-item score are in the repository. One seeded command
> rebuilds the corpus.

**"Is your sensitive test set synthetic?"**
> Yes, so recall is an upper bound. The benign set is real human text, which is why the
> false-positive rate is the number we stand behind.

**"How does that compare with existing DLP?"**
> Honestly, not as simply as we'd like. The common 51% figure counts wrong alerts; ours counts
> wrongly blocked pastes. Converted like for like, we're in the same range — better if more
> than about 4% of pastes are sensitive, worse if fewer. What we add is a number published
> with its denominator, so it can be checked.

**"What about images?"**
> The image path works end to end — it blocked one of our test charts — but with the 30B
> vision model on the box it takes 10 to 20 seconds, so it isn't interactive. And our demo
> chart did *not* block: the model described the confidential markers but wouldn't quote
> them, so our verification refused to block. We cut it from the recording rather than fake
> it.

**"Does the local model see the confidential data?"**
> Yes — the full paste goes to the local 30B so it can answer the actual question. That's the
> point: it's on the same machine and nothing is sent off it. The decision log keeps an
> encrypted copy, capped at 8 KB, only so an analyst's correction can be learned from.

**"How do we know nothing went to the cloud?"**
> For the agent sandbox, the platform's own log: one inference endpoint, local; the cloud
> APIs denied at the proxy. For the host service, the claim is architectural — it only
> listens on loopback and reports zero bytes sent on every verdict. We planned to prove that
> part by unplugging the network on stage and never captured it, so we don't claim it.

**"What would you do next?"**
> Strip redaction masks like `XXXX` before classification — that's the biggest error class.
> Re-run the evaluation with the scoring fix we made after the run, so the threshold
> actually does something. And a smaller vision model so images are interactive.
