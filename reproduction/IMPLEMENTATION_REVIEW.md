# Implementation review — 2026-11-17

Scope: AlphaDiana Metaⁿ harness, generation boundary, isolation/scoring, recovery, accounting and delivery. No paid requests were made during review. Historical raw outputs and scores were retained.

## Material finding: attachment generator differed from upstream

The historical `scripts/meta_n/campaign.py` used `Trace.depth=len(parent)` and generated a layer at `depth=len(parent)+1`. It also omitted `previous_scores`. Upstream numbers the base solver 1, the first strategy 2 and the second 3. Its OmegaEngine selects `OMEGA_PROMPT_META` only when depth≥3 **and** previous_scores is supplied. Thus the historical C generation used the raw-trace template rather than that higher-order summary branch.

The historical pilot, MATH-500 formal run, CO-Bench smoke and corrected CO-Bench A/B/C run use that adapter variant. Their results are observations of the recorded implementation, not faithful tests of the upstream higher-order prompt behavior. The earlier description “valid comparison” referred to the restored resource contract and selection protocol; it was insufficient to establish method fidelity. Do not use these results to reject Metaⁿ generally.

Forward fix: base trace depth 1; A/B depth 2; C depth 3. C receives pre-A baseline scores and current A scores. Runtime layer events now follow upstream depths 3→2→base. New artifacts store upstream_depth and baseline_rows_hash. An old parent without this convention cannot be extended by the new generator. Existing completed artifacts can be read, but remain historical.

An offline test runs the real OmegaEngine with a fake transport and checks that C actually uses the higher-order depth-3 prompt. It also verifies baseline provenance and rejects missing baseline feedback. No new endpoint result is claimed for this fix.

The 8k/16k experiments in `recursive_ablation*.py` use official EvolutionaryOrchestrator, which already supplies parent/grandparent scores and uses base=1. They are unaffected by this specific finding. They remain limited by small data, a single search seed, unequal compute and other documented protocol differences.

## Accounting and failure-state fixes

- Halt-file rejection previously happened outside the journaling try/finally and left an attempt marked running. It is now finalized without a request, retaining the original halt reason.
- A provider response missing usage previously raised before the raw response was copied into the failure journal. Failures now retain the received response, known usage, reservation and whether a request was sent. Cancellation is recorded as well.
- Journal writes use temporary-file replacement. Reservation remains locked and fsynced before network dispatch. Ambiguous outcomes retain their reservation; SDK retries remain disabled.
- The generic numeric executor now handles macOS post-exit process-group PermissionError as the CO-Bench worker already did.
- A CO-Bench batch infrastructure timeout and non-finite score now raise for audit instead of being treated as a model-quality score of zero. The official eval_func/norm_score are not changed.

## Confirmed contracts

- Solver receives task ID and problem only, not ground_truth, reference solution or arbitrary task metadata. Scoring is outside the solver.
- C executes before A, A receives outer_context, deeper same-name helpers override earlier helpers, and the original injection object is not mutated.
- Truncation is retained, not executed. A historical recovery bug produced one extra flat output; it remains excluded from metrics and included in physical cost, with the original truncation scored zero.
- Tests now use synthetic local fixture data instead of depending on the researcher's sibling MATH-500 artifacts. Fixture data is only for tests, not reported experiments.
- Shared registration imports do not require Metaⁿ until its harness is selected. The optional source dependency is pinned to upstream commit b7081843d3c7b0e0f418ca10aaf2ccbff856e7f8.

## Delivery limits

The sandbox is macOS-specific, not a portable container boundary. Parent batch deadlines are derived from the official instance count; per-instance limits remain fixed. The pure mathematical executor has separate CPU and wall-clock limits documented in the original pilot guide. Model aliases and temperature settings do not ensure deterministic responses.

The historical snapshots contain absolute local paths and implementation hashes. They are evidence, not relocatable cached campaigns. Review the exported artifacts without rerunning them under changed source; start a separately frozen campaign for any new paid experiment. Current fixes have offline/fresh-environment validation only.

## Validation completed

32 targeted and registry tests pass. A fresh checkout was reconstructed from the base plus staged patch, with a new Python 3.11 venv and pinned upstream clone, without the existing experiment directory. All 32 tests and CLI help passed; no model calls were made. The first clean run exposed a temporary-venv sandbox deny: runtime allowlists now apply to the temporary-directory clause as well, while unrelated temporary/user files remain denied. The failed attempt and successful rerun are retained in the review debug group.

The clean test verifies installation, harness contracts and offline generation, not endpoint efficacy of the new generator. Historical scores were not recomputed after review.
