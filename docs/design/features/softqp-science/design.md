# Design: native soft-QP execution and immutable experimental evidence

This document reconciles the current pipeline, local edit and scientific evidence paths. It describes implemented interfaces and proof obligations without claiming that this design existed before their code. Its central invariant is that compatible methods solve the same original objective and hard-row policy; unsupported semantics remain explicit rather than being silently converted to another problem.

## Inputs, methods and original evaluation

`pipeline.softqp_cases.cases` supplies fifteen distinct authored cases, including scalar side prices, hard/soft mixtures, sparse numerical families, double-integrator control and attributed building-energy structure. `pipeline.softqp_run.run_case` chooses compatible methods, calls the separate public numerical engine and constructs result entries with states and reasons. The reference representation supports selected grouped or mixed objectives where the ordinary separable `Problem` cannot be substituted without changing semantics.

`pipeline.io.contract.decode_problem` admits sparse original inputs before native setup. The case specification uses CSC matrices and per-row lower/upper linear/quadratic coefficients with a hard/soft mask. Missing sides decode from null to the correct signed infinity. Matrices, vectors, units and policy remain original-coordinate data. `pipeline.optimality.kkt` checks both recovered stationarity and the interval-penalty proximal relation; stationarity alone does not certify a correctly priced soft optimum.

`pipeline.control.predict_states` propagates the actual double-integrator inputs without clipping. This is a deterministic physical model, not a trained forecast. A returned point can intentionally depart from a soft interval while preserving a hard actuator bound. Numerical correctness and policy choice are separate questions, and neither alone establishes plant safety.

## Export and bounded local changes

`pipeline.softqp_run.bake` writes a checksummed scientific index and one result per case into an explicitly supplied output root. `pipeline.pipeline.STAGES` names validate, assemble, solve, evaluate and export responsibilities; these are not separate CLI subcommands. The top-level CLI runs the complete bake with `all` or recomputes `readiness`, and performs no model training. `pipeline.core.manifest.export_manifests` declares deployable compact artifacts, and readiness derives their actual availability. The static web replays those results; it does not claim to execute the native solver in the browser.

`pipeline.softqp_requests.execute_request` validates a bounded solve request, checks the referenced original result digest and compares the serialized original problem to the actual authored catalog. Only supported separable cases admit cost editing. Lower and upper multipliers change soft prices while hard rows remain unchanged; a zero quadratic multiplier explicitly requests a pure linear family and admits the corresponding compatible comparison paths. Grouped inputs are refused rather than flattened.

The result envelope contains the request, complete case result and actual numerical environment. `frontend/src/lib/softqp.local.ts` validates it, verifies its intended input and independently reconstructs original objective and departures before the workbench displays it. A malicious file that changes its request, matrices, mask or reported metrics is refused. Native output remains a locally executed import with that provenance, never a browser solve.

## Stream and campaign evidence

`pipeline.softqp_stream.run_stream` retains thirty-two common-input frames with separate cold/warm states and setup/update costs. `pipeline.experiment_export.verify_campaign` checks the complete instance/method/repetition matrix and recomputes summaries from raw trials before publication. A deleted observation remains detectable even when outer checksums are recomputed. The frozen separable campaign and subsequent directional campaign are distinct authorities with negative registered outcomes; this pipeline description does not retune them or join their denominators.

The schemas named by `softqp-index`, `softqp-case-result`, `softqp-case-spec`, `softqp-run-request`, `softqp-local-export`, `softqp-stream` and the experimental catalog rows specify these boundaries. Failure states, genuine incompatibilities and missing values survive serialization. A failed run is not an optimal solution with a zero cost.

## Alternatives and requirements

Silently symmetrizing side costs, regularizing an incompatible objective or clipping a control was rejected because each changes the original problem. Comparing timing across different penalty families was rejected because it compares policies, not implementations. Trusting checksums without reconstructing the complete population was rejected because a rehashed omission can bias an endpoint.

SQ-001 through SQ-004 map case coverage and native/lifted parity to `tests/test_softqp_matrix.py` and hostile scientific-boundary tests. SQ-005 through SQ-007 map bounded requests and imports to their Python and TypeScript tests. SQ-008/SQ-009 cover complete stream/experiment exports; SQ-010/SQ-011 cover original optimality and physical predictions. [Validation](validation.md) names the concrete falsifications and [tasks](tasks.md) their dependency graph. Actual numerical regression and full evidence replay remain required acceptance beyond the presence of these mappings.
