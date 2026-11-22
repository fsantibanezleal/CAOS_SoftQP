# Dependency graph and convergence: softqp science

The authored case and original objective must be fixed before compatibility and numerical comparison. Original-space evaluation precedes export; local edits are admitted only against that same source. This graph describes current production responsibilities without rerunning either frozen timing study.

## Dependency sequence

| Unit | Requires | Requirements | Implementation responsibility | Production and test files |
|---|---|---|---|---|
| S1 | None | [SQ-001](requirements.md), [SQ-002](requirements.md), [SQ-003](requirements.md) | Enumerate unique cases and execute compatible equivalent formulations | `data-pipeline/pipeline/softqp_cases.py`; `data-pipeline/pipeline/softqp_run.py`; `tests/test_softqp_matrix.py` |
| S2 | S1 | [SQ-010](requirements.md), [SQ-011](requirements.md) | Evaluate original optimality and physical predictions without clipping | `data-pipeline/pipeline/optimality.py`; `data-pipeline/pipeline/control.py` |
| S3 | S1, S2 | [SQ-004](requirements.md) | Export results into the explicitly selected root and bind all bytes | `data-pipeline/pipeline/softqp_run.py`; `tests/scientific/test_softqp_boundary.py` |
| S4 | S3 | [SQ-005](requirements.md), [SQ-006](requirements.md), [SQ-007](requirements.md) | Execute bounded local requests and verify returned imports | `data-pipeline/pipeline/softqp_requests.py`; `frontend/src/lib/softqp.local.ts` |
| S5 | S1, S2, S3 | [SQ-008](requirements.md), [SQ-009](requirements.md) | Retain complete stream pairing and experimental populations | `data-pipeline/pipeline/softqp_stream.py`; `data-pipeline/pipeline/experiment_export.py` |

## Exact requirement gates

Each requirement retains its own positive/behavioral gate and its distinct hostile check in [validation](validation.md). This table is an interface-to-proof map; it makes no claim that an unobserved command passed.

| Requirement | Dependency unit | Required gate from the current specification | Current convergence boundary |
|---|---|---|---|
| [SQ-001](requirements.md) | S1 | `tests/test_softqp_matrix.py::test_case_catalog_covers_fifteen_declared_ids` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [SQ-002](requirements.md) | S1 | `tests/test_softqp_matrix.py::test_scalar_methods_share_objective_and_hard_policy` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [SQ-003](requirements.md) | S1 | `tests/test_softqp_matrix.py::test_grouped_reference_matches_explicit_lift` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [SQ-004](requirements.md) | S3 | `tests/test_softqp_matrix.py::test_bake_writes_hashed_inventory_outside_committed_data` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [SQ-005](requirements.md) | S4 | `tests/test_softqp_requests.py::test_local_request_recomputes_a_changed_optimum` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [SQ-006](requirements.md) | S4 | `tests/test_softqp_requests.py::test_adversarial_stale_and_grouped_requests_are_rejected` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [SQ-007](requirements.md) | S4 | `frontend/src/lib/softqp.local.test.ts::accepts the actual native producer and independently verifies original costs` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [SQ-008](requirements.md) | S5 | `tests/test_softqp_stream.py::test_c12_complete_pairing_and_accuracy` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [SQ-009](requirements.md) | S5 | `tests/test_experiment_export.py::test_experimental_exports_and_provider` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [SQ-010](requirements.md) | S2 | `tests/test_softqp_optimality.py::test_original_kkt_on_solver_and_scaled_rows` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [SQ-011](requirements.md) | S2 | `tests/test_softqp_control.py::test_predictor_retains_input_and_physical_dynamics` | Implementation mapped; current gate execution is a separate acceptance obligation. |

## Current convergence

All listed responsibilities have real modules and positive/hostile controls. Exact native SDK identity, original-space parity and full matrix/population validation are load-bearing checks. The engineering vertical can be implemented while the registered timing criterion is false; no iteration count, smaller representation or corrected document changes that result.

The design in [design.md](design.md), all current requirement rows and their validation rows are explicit. Structural document checks verify these links and identifiers. They do not substitute for executing the functional gates or for independently reviewing a changed numerical or visual result.
