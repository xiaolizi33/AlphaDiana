# Reviewed A/B/C rerun — 2026-11-18

Both formal campaigns completed with fresh endpoint outputs after the depth and baseline-feedback fix. [Results](RESULTS.md) report the MATH-500 and CO-Bench scores. [Completion audit](COMPLETION.md) maps the current deliverables to the mini-project requirements.

The `math500/` and `cobench/` directories expose protocols, selections, metrics and generation audits. `raw_records.tar.gz` contains complete strategy requests/responses, generated strategy code, all Diana result rows and configurations, runtime trajectories, a new mathematical recursive case, token accounting, and debug command/source snapshots. `RAW_MANIFEST.json` lists the SHA-256 and size of each archived file.

From this directory, verify the archive with `shasum -a 256 -c raw_records.sha256`. From the workspace containing sibling `AlphaDiana/`, `meta-n/` and `experiments/`, extract with `tar -xzf AlphaDiana/reproduction/review_rerun_20261118/raw_records.tar.gz`. The archive's `experiments/` paths refer to the original recorded campaigns. Absolute paths in saved configurations document that environment.

For fresh endpoint reproduction, follow the installation instructions in the [reproduction guide](../README.md), prepare the original dataset snapshots using the [experiment guides](../../configs/meta_n/README.md), set `DEEPSEEK_API_KEY`, then run from the workspace root

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/debug_run.py --group review_rerun --label math500 -- .venv/bin/python AlphaDiana/scripts/meta_n/rerun_review.py --campaign math500 --stage all
.venv/bin/python AlphaDiana/scripts/meta_n/debug_run.py --group review_rerun --label cobench -- .venv/bin/python AlphaDiana/scripts/meta_n/rerun_review.py --campaign cobench --stage all
```

These commands use the separately frozen `math500_review_20261118` and `cobench_review_20261118` scopes. The MATH-500 runner reads the original `experiments/math500_formal/protocol.json` and prepared snapshot. The CO-Bench runner reads `experiments/cobench_corrected_data`. Install and prepare those inputs before running. The original experiment guides describe their preparation. Running in a fresh output directory generates new model calls and reserves additional budget. Saved completed runs resume from their recorded outputs.
