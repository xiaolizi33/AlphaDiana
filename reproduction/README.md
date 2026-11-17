# Metaⁿ integration and recorded experiments

This fork implements the mini-project's AlphaDiana harness and A/B/C selection structure, and includes a scaled official archive-versus-flat ablation. Read [问题复盘（中文）](ISSUES_AND_LESSONS.md) and [implementation review](IMPLEMENTATION_REVIEW.md) first: review found and fixed an upstream-depth/baseline-payload discrepancy in the historical attachment generator. Historical numerical results have not been regenerated after that fix.

## Install

Use macOS with `sandbox-exec`, Xcode Command Line Tools Python, uv and Python 3.11. Arrange the workspace as:

```text
workspace/
  AlphaDiana/       # this fork
  meta-n/          # pinned official source
  experiments/     # optional recorded-artifact archive; new runs write here
  notes/           # optional research notes
```

From `workspace`:

```sh
git clone https://github.com/minnesotanlp/meta-n.git meta-n
git -C meta-n checkout --detach b7081843d3c7b0e0f418ca10aaf2ccbff856e7f8
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r AlphaDiana/configs/meta_n/requirements-reproduction.lock
uv pip install --python .venv/bin/python --no-deps -e ./meta-n -e ./AlphaDiana
.venv/bin/python -m pytest AlphaDiana/tests/harness/meta_n -q
```

The lock captures the tested macOS/Python environment. The project also exposes `.[meta-n]` for installing the pinned public Git dependency; the sibling checkout is needed by the historical campaign commit-provenance checks. Other Diana harnesses can be used without selecting that extra.

## Offline inspection and verification

Tests use fake model transports and local fixtures; no API key or dataset download is needed. `tests/fixtures/meta_n` contains synthetic test-only data. Solver execution tests use the real macOS sandbox. For debugging, always wrap commands:

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/debug_run.py --group review --label tests -- .venv/bin/python -m pytest AlphaDiana/tests/harness/meta_n -q
```

The wrapper records commands, source snapshots/hashes, complete stdout/stderr and return codes under the workspace's `experiments/debug_runs/`. API requests additionally retain request IDs, response JSON and usage. Read [experiment commands](../configs/meta_n/CORRECTED_AND_ABLATION.md) before any paid run. Set DEEPSEEK_API_KEY in the environment. The original experiments have known legacy key-file fallbacks; no key file is part of this submission.

## Recorded outcomes

|Experiment|Metric|Result|Scope|
|---|---|---|---|
|MATH-500 attachment variant|Test accuracy|base 50/60; two executions of selected A 45/60 and 46/60|Legacy Omega depth/payload variant; same A difference is sampling variation|
|Resource-corrected CO-Bench variant|Held-out mean quality|base .824347; independent/recursive both select A .821867|9 task families total; legacy Omega depth/payload variant|
|16k official archive ablation|Validation quality|archive and four flat draws both .991977|3 task families, 3 search iterations, 13 archive candidates; max upstream depth 4|

No general recursion advantage was established. A depth-3 example repairs a parent CDD score .513014→.975931, on validation tasks used in search. It illustrates execution and code replacement, not held-out benefit or isolated causality. Archive-best and best fixed chain are separate estimators. The 8k precursor never generated a depth≥3 candidate; its score gap is not evidence for higher-order recursion.

The companion artifact archive preserves original protocols, strategy code, request/response journals, per-task scores, figures, debug records, source snapshots and cost audits. `SUBMISSION_MANIFEST.json` in the workspace artifact bundle lists every included file hash. Public datasets are attributed to their upstream sources; no new dataset license is asserted here. There are no included credentials or virtual environments.

## Code walkthrough

- `alphadiana/harness/meta_n/agent.py`: task allowlist, base solver, strategy chain, AgentResponse.
- `layers.py`: official composition, isolated preprocessing, helper collision semantics.
- `executor.py` / `co_bench.py`: numeric execution vs official continuous optimization scoring.
- `client.py`: request journals, pre-dispatch reservation, usage and failure accounting.
- `scripts/meta_n/campaign.py`: Omega input provenance and baseline feedback.
- `formal_campaign.py` / `cobench_corrected.py`: split isolation, D selection then T freeze.
- `recursive_ablation_16k.py`: official evolutionary search vs four flat draws; scaled protocol and departures.

The repository is prepared locally for review. It has not been pushed to the upstream tmlr-group remote.
