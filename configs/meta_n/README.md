# Metaⁿ reproduction

Start with [submission and review guide](../../reproduction/README.md).

- [Implementation review](../../reproduction/IMPLEMENTATION_REVIEW.md): audited semantics, fixes and historical-result qualifications.
- [MATH-500](MATH500.md): fixed public dataset and original attachment experiment.
- [Corrected CO-Bench and scaled ablation](CORRECTED_AND_ABLATION.md): protocols, commands and result boundaries.
- [Original zero-layer engineering pilot](ZERO_PILOT.md), [strategy generation pilot](STEP23.md), [pilot test](STEP4.md): historical development records, not formal efficacy evidence.

The review on 2026-11-17 corrected the attachment generator's upstream depth numbering and baseline-score payload. Historical A/B/C runs used the earlier variant; their scores remain unchanged. Do not describe them as faithful execution of the upstream higher-order prompt branch. The official evolutionary-orchestrator 16k experiment used correct upstream numbering already. New generator behavior has offline contract tests but has not been re-run against the paid endpoint.
