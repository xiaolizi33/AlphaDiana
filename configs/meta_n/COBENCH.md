# CO-Bench paper-data smoke

This is a separately frozen six-task engineering experiment using the dataset from the paper, not its full numerical reproduction. The previous MATH-500 experiment remains intact.

Use the existing AlphaDiana and pinned sibling Metaⁿ installation. Additional evaluation dependencies: numpy, scipy, networkx. macOS `sandbox-exec` is required. Model-generated programs use Python's standard library; the official loaders/evaluators may use numpy. No inner LLM calls are enabled.

From the workspace root:

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/prepare_cobench.py
.venv/bin/python AlphaDiana/scripts/meta_n/cobench_campaign.py --stage validate
.venv/bin/python AlphaDiana/scripts/meta_n/cobench_campaign.py --stage all
```

`validate` runs known-invalid programs through the official scorer without model calls. `all` makes paid requests under the existing global ¥50 reservation guard and a separate ¥6 scope cap. Set `DEEPSEEK_API_KEY` in the environment; the existing local key-file fallback is also supported. Never commit that file.

Source: CO-Bench/CO-Bench at revision `6e561a36254d4315b8c2d155e81a465b634e87e1`. Each selected family uses only its lexicographically first official instance file. G: bin packing, flow shop. D: graph colouring, job shop. T: open shop, aircraft landing. G/D use upstream dev indices; T uses upstream test indices. No synthetic instances are generated. Task-family splits are disjoint. This subset was fixed before paid requests and is intentionally small.

Diana dispatches tasks through `meta_n_co_bench`; the harness returns the generated algorithm without invoking a no-argument `solve`. `co_bench_official` then invokes the upstream `_TaskEvaluator`, including `load_data`, `eval_func`, `norm_score` and `get_dev`, in a separate sandbox process without API keys or network. Per-instance timeout is 3 seconds and per-task timeout 180 seconds. The local macOS sandbox is not a portable container boundary.

The metric is the official **continuous normalized optimization score**, not accuracy. The generic Diana `correct` field indicates only a positive score. Candidate selection uses mean continuous score, then shallower chain, then A. The same selected chain reuses the same test outputs across branches. Results and configuration YAMLs are stored under `experiments/cobench_paper_smoke`; `selection.json` and `test_manifest.json` are frozen before T evaluation. No repair generations or test-guided candidate changes are permitted.

The small subset, single search seed, new backbone, limited standard-library dependency contract and lower execution timeout differ from the paper. Report results as a flow test and inspect the per-task quality scores. A positive result would motivate a larger frozen experiment; it would not establish the paper's broad claims.
