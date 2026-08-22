# policy/exclusions.md — owner C. SRS §S2.1 artifact (2) of 3.

**The move almost nobody makes.** Every other team will *add* egress. We *remove*
NVIDIA's own baseline, and we record what removing it costs.

---

## Why this is the interesting artifact

Adding an allow rule proves you read the docs. Removing a baseline rule proves you
understood what the baseline was *for* — because `policy exclude` refuses to proceed
without a reviewed feature-impact disclosure. The platform makes you say, in writing,
which supported features you are choosing to break.

`policy exclude` also:

- previews the egress **and the named supported features that will stop working**,
- binds a **versioned exclusion record** to the reviewed baseline content and the
  active agent,
- **replays it on every rebuild, failing closed if the baseline or the agent changed.**

That last property is the one worth saying out loud: our removals are as reproducible
as our additions, and they refuse to silently reapply against a baseline they were not
reviewed against.

---

## VERIFY-AT-10:00 — read the real rule names, do not guess

The brief and the NemoClaw research disagree about the baseline: the **five-endpoint**
list is NemoClaw's; the larger list including `github.com` and `api.anthropic.com` is
bare OpenShell's `sandboxes/base/policy.yaml`. Resolve it by reading, not by assuming:

```bash
nemoclaw airlock policy list        # capture the EXACT rule names into the table below
```

Paste the real output here at 10:05 before touching anything:

```
<paste `nemoclaw airlock policy list` output here>
```

---

## The exclusions we intend

| # | Baseline rule | Why we remove it | Feature we accept losing |
|---|---|---|---|
| 1 | `<nvidia_api_rule>` | `integrate.api.nvidia.com` is a remote inference endpoint. Rule 02 forbids remote LLM calls in the agent runtime path. Leaving it allowed means our strongest claim rests on "we did not call it" rather than "it could not be called." | NVIDIA-hosted NIM inference. We do not use it; our inference is host-local. |
| 2 | `<npm_rule>` | Package installation is a build-time need, not a runtime one. Once skills are installed, a live path to `registry.npmjs.org` is standing supply-chain surface for no benefit. | Runtime `npm install`. Excluded **only after** skills are installed — order matters. |

`managed_inference` **cannot** be excluded and we do not want to: that is the
`inference.local` route to our own 35B on the host.

---

## Commands

```bash
# 1. NVIDIA's remote inference endpoint
nemoclaw airlock policy exclude <nvidia_api_rule> --dry-run
nemoclaw airlock policy exclude <nvidia_api_rule> --force

# 2. npm — AFTER `nemoclaw airlock skill install` and `openclaw skills install` have run
nemoclaw airlock policy exclude <npm_rule> --force

# 3. Capture the resulting posture as evidence
nemoclaw airlock policy explain --json | tee evidence/airlock-policy.json
```

---

## Fallback if `policy exclude` refuses

**Do not spend more than ten minutes here.** Leave the baseline intact and fall back to
evidence instead of configuration:

> `integrate.api.nvidia.com` is never called, and we prove it from the OCSF log rather
> than from the policy file — `evidence/rule02-providers.txt` is the output of
> `jq -r 'select(.class_uid==6003) | .ai_model.ai_provider' | sort | uniq -c` over the
> full run: one provider, `host.openshell.internal`, zero cloud LLM hosts.

That is arguably the stronger artifact anyway: a configuration says what you intended,
a log says what happened.

---

## What we say in the submission

> We removed two rules from NVIDIA's own baseline rather than only adding our own, and
> the platform made us file a feature-impact disclosure to do it. The exclusion record
> is versioned, bound to the baseline content it was reviewed against, and replayed on
> every rebuild — failing closed if that baseline or the active agent has changed.
