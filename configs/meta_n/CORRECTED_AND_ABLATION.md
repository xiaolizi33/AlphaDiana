# Corrected comparison and DeepSeek recursion ablation

All old artifacts remain intact. Debugging invocations are recorded by `scripts/meta_n/debug_run.py`: command, source copies/hashes, stdout, stderr, return code and duration. API requests are separately journaled by request_id, which also appears in the budget-reservation ledger. No key values are logged.

## Corrected attachment-style comparison

Official CO-Bench revision: `6e561a36254d4315b8c2d155e81a465b634e87e1`.
G/D/T use disjoint task families absent from the previous smoke. Each uses one official file; G/D use dev indices, T uses an official non-dev file. The empty-test preliminary selection is archived and was fixed before model requests.

`ResourceContract` is the shared source for model prompts and evaluation: 10 seconds per instance, at most 5 seconds total in helpers. The scorer's parent deadline covers the number of instances times the per-instance bound plus startup allowance; it is not a smaller hidden solver budget. The solver is standard-library only, with array-like inputs supplied by official loaders. No inner LLM calls.

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/debug_run.py --label prepare -- .venv/bin/python AlphaDiana/scripts/meta_n/prepare_cobench_corrected.py
.venv/bin/python AlphaDiana/scripts/meta_n/debug_run.py --label validate -- .venv/bin/python AlphaDiana/scripts/meta_n/cobench_corrected.py --stage validate
.venv/bin/python AlphaDiana/scripts/meta_n/debug_run.py --label compare -- .venv/bin/python AlphaDiana/scripts/meta_n/cobench_corrected.py --stage all
.venv/bin/python AlphaDiana/scripts/meta_n/debug_run.py --label report -- .venv/bin/python AlphaDiana/scripts/meta_n/report_corrected.py
```

Artifacts: `experiments/cobench_corrected/`. A/B share identical base traces. C sees A source plus newly scored G/A. Invalid candidates are retained, with no repair generations. Select A/B and A/A+C on D, freeze selection then evaluate T. If both select A, reuse the same outputs. Continuous normalized optimization quality is the metric; generic `correct` means only positive score and is not mathematical correctness.

One PermissionError during scorer-process cleanup was repaired by re-evaluating the identical saved program. Original JSONL remains untouched; `score_repairs` overlays the repaired score after validating the original row hash. Implementation changes are separately recorded in `implementation_amendments`. No extra model draw was used.

## Scaled paper-method ablation

The paper's appendix C uses an evolutionary archive for full Metaⁿ and, for its GPT-5.2 depth-1 control, four independent draws at temperature 1.0 with no library or context injection. This run exercises those two pipelines with DeepSeek. It does not reproduce original numerical results or matched compute.

Full branch uses upstream `EvolutionaryOrchestrator`, B=2/K=2, epsilon=.02, alpha=.3, Ω temperatures .5/.7/.9, depth cap 10 and up to two self-debug retries below score .1. Scaled settings: 3 G task families, one official file each, 3 evolutionary iterations, one search seed (42), gates disabled. On the newer upstream, library injection is explicitly enabled to preserve the paper's intended channel. Preprocessing and program evaluation run in macOS sandbox workers. No held-out evaluation: these are validation metrics, consistent with the paper's depth-1 ablation estimator.

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/debug_run.py --label offline -- .venv/bin/python AlphaDiana/scripts/meta_n/verify_ablation_offline.py
.venv/bin/python AlphaDiana/scripts/meta_n/debug_run.py --label ablation -- .venv/bin/python AlphaDiana/scripts/meta_n/recursive_ablation.py --stage all
```

Artifacts: `experiments/deepseek_recursive_ablation/`: protocol, four `depth1` draws, full archive/checkpoints/lineage, request journals, layer events and comparison. A truncated flat draw was retained and scored zero, without execution or replacement; partial completed task outputs were recovered. Do not report archive-best as a deployed fixed chain or as held-out accuracy.

## Cost and resumption

The user authorized continued DeepSeek usage beyond the original ¥50 cap. New scopes have conservative operational guards (corrected ¥12; ablation ¥30 per branch; global guard ¥150). These are reservation guards, not actual bills or planned spend. Every response's raw usage is retained. Existing experiments keep their original default ¥50 guard.

The corrected comparison resumes scored outputs and audited score repairs. Incomplete ablation flat draws recover saved task outputs and retained truncations; the full archive halts for audit if an incomplete attempt exists, rather than silently restarting a paid search.

## Output-cap follow-up and audit

The 8192-token ablation produced seven truncated Ω outputs and never built a depth≥3 candidate. Its archive-best gap must not be interpreted as evidence for higher-order recursion. A recovery matching bug also caused one extra flat-program draw; that output was excluded from metrics and retained in `recovery_audit` along with its cost. The original truncated draw scores zero.

A separately frozen follow-up uses 16384 output tokens (upstream CLI default) on **both** branches, with 180-second request timeout. It uses fresh independent draws and keeps every prior result:

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/debug_run.py --label ablation-16k -- .venv/bin/python AlphaDiana/scripts/meta_n/recursive_ablation_16k.py --stage all
.venv/bin/python AlphaDiana/scripts/meta_n/debug_run.py --label report-16k -- .venv/bin/python AlphaDiana/scripts/meta_n/report_ablation_16k.py
```

Output: `experiments/deepseek_recursive_ablation_16k/`. Comparing 8k vs 16k scores does not isolate the cap's effect, because model responses were independently sampled and no deterministic request seed was sent. Report both runs. Runtime dependency versions are in `environment.json`; install `requirements-co-bench.txt` for the numerical/plotting dependencies alongside the pinned project installations.
