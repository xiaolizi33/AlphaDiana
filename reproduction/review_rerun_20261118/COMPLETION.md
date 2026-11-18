# Mini-project completion audit — 2026-11-18

The implementation and two reviewed formal campaigns are complete. The presentation deliverable remains pending.

|Requirement|Status|Evidence|
|---|---|---|
|Task A, Diana-loadable solver, configuration, answer/trace/usage, original mathematical scorer|Complete|Metaⁿ harness, generated run configs, 270 MATH-500 valid-scored rows|
|Fixed mathematical G/D/T and base|Complete|MATH-500 G10/D20/T60 protocol and snapshot digest, fresh base outputs|
|Task B, official Ω, A and C generation, A+C execution|Complete after review fix|A/B upstream depth 2, C depth 3, real higher-order prompt and baseline hash verification|
|Task C, shared base/A, independent B, recursive C, development selection, frozen test|Complete|Protocols, request messages, selection and test manifests; equal opportunity/caps, actual tokens reported|
|Test accuracy and paired changes|Complete|Base 44/60, two selected-A executions 56/60 and 52/60; fixed/regressed 12/0 and 10/2|
|Separate generation and solving tokens|Complete|math500/token_breakdown.json; shared calls counted per branch and once physically|
|Mathematical C code/trajectory example|Recorded and explained below|Archived recursive_case_study.json from the reviewed MATH-500 D split|
|Repository, harness, generation entry and three-group configs, setup instructions|Prepared for repository delivery|Tracked source and guides, archived complete run configurations|
|Strategy code, per-task results and case trajectories|Prepared for repository delivery|raw_records.tar.gz and per-file SHA-256 manifest|
|15–20 minute presentation|Pending|Workspace notes/03_talk_outline.md remains a preparation outline; no completed slide deck was found|

The reviewed mathematical example is development task `test/prealgebra/1646.json`, chosen as the first task correct with A and wrong with A+C. It asks for an angle in a quadrilateral whose two other angles are 110° and 100°. The trisected angles sum to 150°, and triangle AFD has the two relevant angles totaling 100°, so its third angle is 80°. A generated `solve()` returning 80. A+C generated `solve()` returning 130.

C read A's source and the new G/A feedback, whose mean score was 1.0, together with the pre-A baseline scores. Its generated preprocessor classified symbolic answer types and added guidance to call `finalize_answer` for symbolic outputs. That helper was present in the composed program. The runtime events show C at depth 3 followed by A at depth 2, with A receiving 2,979 characters of outer context. Both programs returned numeric constants and did not call the new helper. This records context propagation and an observed regression. A single pair of generated programs cannot establish which instruction caused the changed answer. The full code, strategy inputs and runtime events are archived.

MATH-500 selected A for both branches, so its two test scores describe separate executions of the same selected strategy. CO-Bench selected A versus A+C and scored 0.664186 versus 0.764236, with base 0.832881. Each campaign has one search run. The mathematical test set has 60 problems, and CO-Bench has three held-out task families.

The reviewed rerun produced 297 valid-scored rows and 303 completed request journals. Its reservations reconcile to ¥34.825719. The recorded Metaⁿ suite passed 31 tests. An earlier clean-checkout installation review passed 32 targeted/registry tests. The rerun wrapper itself was exercised end to end in the current environment.

A final slide deck incorporating these reviewed results and this mathematical case is still required to satisfy all submission deliverables.
