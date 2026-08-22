# RUNBOOK-C — dry-run findings from B

B ran the **read-only** parts of `RUNBOOK-C.md` on the box. Stopped before anything that
mutates state. Raw output in `evidence/`.

**Headline: the runbook fails at its first probe.** Several `nemoclaw` and `openshell`
invocations in it do not exist in the versions installed here. This is a ten-minute fix
now and a very bad ten minutes at 10:00.

Installed: `nemoclaw v0.1.0`, `openshell` (sandbox reports `openshellVersion 0.0.44`),
`openclaw`. `mongosh` is **not installed**. `jq` is.

---

## 1. There is no sandbox called `airlock`

```
$ nemoclaw list --json   ->   "defaultSandbox": "my-qwen-claw"
                              "lastOnboardedSandbox": "my-qwen-claw"
```

Every `nemoclaw airlock <verb>` line in the runbook — exec, policy, logs, status, skill
install — targets a sandbox that does not exist yet. They only start working after
`nemoclaw onboard --name airlock` succeeds. Worth stating in the runbook explicitly,
because the failure mode is a confusing "unknown sandbox" rather than "run onboard first".

## 2. Command names that do not exist in this build

| runbook says | this build wants |
|---|---|
| `nemoclaw host probe --json` | **no `host` command at all** → `Unknown command: host`. Nearest is `nemoclaw status --json` (saved to `evidence/nemoclaw-status.json`) |
| `nemoclaw profiles list --json` | no `profiles` command. Nearest is `nemoclaw list --json` |
| `nemoclaw agents list` | `nemoclaw <name> agents list` — sandbox name is required |
| `nemoclaw airlock policy add …` | `nemoclaw <name> policy-add …` (**hyphen**, not a subcommand) |
| `nemoclaw airlock policy list` | `nemoclaw <name> policy-list` |
| `nemoclaw airlock policy explain --json` | `nemoclaw <name> policy-explain --json` |
| `nemoclaw airlock policy exclude <rule>` | **no `exclude` verb.** Closest is `policy-remove`, which removes a *preset*, not a baseline rule. This is the 13:00–14:30 step that the demo's egress story leans on — worth checking before then, not during |
| `nemoclaw airlock status --json \| jq .openshellVersion` | `nemoclaw <name> status`; note `openshellVersion` sits **inside `.sandboxes[]`**, not at the top level, so the `jq` filter returns `null`. Use `jq -r '.sandboxes[0].openshellVersion'` → currently `0.0.44` |

`nemoclaw <name> exec -- …`, `<name> logs --follow`, `<name> skill install <path>`,
`<name> snapshot …` are all correct as written, once the sandbox exists.

## 3. `openshell settings` syntax is HALF wrong — corrected after running it

**Correction to an earlier version of this file, which said both `get` and `set` reject
`--key`. Only `get` does.**

- `settings set` **does** take `--key`/`--value` — and, at global scope, also needs
  `--yes` in non-interactive mode:
  `openshell settings set --global --yes --key ocsf_json_enabled --value true` ✓
- `settings get` does **not**: the surface is `openshell settings get [--global] [--json] [NAME]`.
  There is no `--key` and no `--show-scope`.

Original note follows.

## 3b. `openshell settings get` syntax is wrong

```
$ openshell settings set --global --key policy_advisor_enabled --value true
$ openshell settings get --key policy_advisor_enabled --show-scope
  error: unexpected argument '--key' found
```

Real surface is `openshell settings get [--global] [--json] [NAME]` — there is no `--key`
and no `--show-scope`. The P2 advisor check and the `ocsf_json_enabled` line in P3 both
need rewriting against `--help` before the day.

Also, the gateway is not up, so settings reads currently fail with
`transport error … Connection refused (os error 111)` regardless of syntax.

## 4. `mongosh` is not installed

The retrieval-verification step in "corpora and retrieval" — the `$listSearchIndexes`
poll for `status:"READY"` and `queryable:true` — cannot run as written. That check is the
one guarding against a `$vectorSearch` silently returning empty results, so it should not
be the thing we discover is missing at 12:00. Either install `mongosh`, or run the same
aggregation through `pymongo`, which is already a dependency.

## 5. State on the box right now

- **MongoDB is not running.** No container, `:27017` closed. Runbook P0 has not been run.
- `af-vllm` is up (~2 h) holding **38.9 GB**; `MemAvailable` **70.9 GB**, well clear of
  the 8 GB NFR-S13 floor — so the 6 GB Mongo container has room whenever C wants it.
- **Swap is on** (`SwapFree 16 GB`). NFR-S2 requires `sudo swapoff -a` before a vLLM
  launch; `af-vllm` came up without it. A's call, flagging only.
- `data/benign_v1.jsonl` is **1000 lines** — the runbook's `wc -l` check passes.
- Existing sandbox `my-qwen-claw` has presets `brew, huggingface, local-inference, npm,
  openclaw-pricing` enabled; **`github` is disabled**, which is what the egress story
  wants (`evidence/nemoclaw-policy-list.txt`).

## UPDATE — the stack is now up. What actually worked

Everything below was run and verified; see `evidence/`.

| step | working command |
|---|---|
| start the gateway | `nemoclaw onboard` gets as far as `[2/8] Starting OpenShell gateway` and leaves it healthy, then fails at `[3/8]` demanding `NVIDIA_API_KEY`. **Do not supply one** — that provider is NVIDIA's cloud endpoint, which is the exact thing Rule 02 forbids. Kill onboard there and configure the local provider by hand. |
| local provider | `openshell provider create --name gb10-vllm --type openai --credential OPENAI_API_KEY=unused --config OPENAI_BASE_URL=http://172.17.0.1:8000/v1` |
| inference route | `openshell inference set --provider gb10-vllm --model airlock-text --timeout 300` |
| create the sandbox | `openshell sandbox create --name airlock --cpu 2 --memory 4Gi --no-tty --no-keep` — memory must be `4Gi`, not `4g`; takes ~2 min |
| exec in it | `openshell sandbox exec -n airlock -- <cmd>` — `-n`, and it is `sandbox exec`, not `nemoclaw airlock exec` |
| OCSF on | `openshell settings set --global --yes --key ocsf_json_enabled --value true` |
| read OCSF | `openshell logs airlock -n 2000 --level debug` — note `-n` here is LINE COUNT, not the sandbox name; the name is positional |

**`host.openshell.internal` does not resolve where the CLI runs its verification**, so
`inference set` fails against it. Use the docker bridge IP. And vLLM published on
loopback only is unreachable from the gateway container at all — `launch_text.sh` now
takes `AIRLOCK_BRIDGE_IP` and publishes on `172.17.0.1` as well.

## What B did NOT run, and why

Everything below mutates shared state, and most of it is C's to own:

- `stack/up_mongo.sh` — C's artifact and C's call. Memory is fine for it; say the word.
- `stack/seed.sh` — drops and recreates collections.
- `nemoclaw onboard …` — 5–15 minute build that changes global state, and it is the step
  that creates the `airlock` sandbox everything else depends on.
- `openshell settings set --global …` — global config, and the syntax is wrong anyway.
- `nemoclaw airlock policy add / exclude` — changes the egress policy the demo asserts.
- **`python bench/build_benign.py --seed 1337` — would overwrite `data/benign_v1.jsonl`,
  the 1000-record corpus just committed as the FP denominator and a §14 attachment.** It
  also wants dumps in `data/dumps/`, which are not present, so a re-run could quietly
  produce a smaller or synthetic corpus. Do not run this without C.
- `bench/run_fpr.py` — needs a live classifier; `:8002`/T2 is down, so every item would
  record as `airlock_unavailable` and the run would be worthless.
