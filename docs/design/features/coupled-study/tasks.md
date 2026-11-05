# Dependency graph and convergence: coupled study

The registered original-space batch and source authority precede worker setup; complete observation reconstruction precedes the primary paired analysis. This graph describes the existing offline implementation, not permission to rerun or revise its frozen experiment.

## Dependency sequence

| Unit | Requires | Requirements | Implementation responsibility | Production and test files |
|---|---|---|---|---|
| P1 | None | [CP-001](requirements.md), [CP-002](requirements.md), [CP-005](requirements.md), [CP-011](requirements.md) | Admit batch schema, exact environment and registered authorities | `data-pipeline/pipeline/coupled_contract.py`; `data-pipeline/pipeline/coupled_freeze.py`; `scripts/check_coupled_requirements.py` |
| P2 | P1 | [CP-003](requirements.md), [CP-004](requirements.md) | Execute equivalent objectives and independently check original metrics | `data-pipeline/pipeline/coupled_campaign.py`; `data-pipeline/pipeline/coupled_accuracy.py` |
| P3 | P1, P2 | [CP-012](requirements.md) | Supervise owned workers with bounded output, time and memory | `data-pipeline/pipeline/coupled_resources.py`; `tests/coupled/test_coupled_registration_and_workers.py` |
| P4 | P2, P3 | [CP-006](requirements.md), [CP-007](requirements.md) | Reconstruct the complete journals, identity and exact CSV | `data-pipeline/pipeline/coupled_export.py`; `tests/coupled/test_coupled_export.py` |
| P5 | P4 | [CP-008](requirements.md), [CP-009](requirements.md), [CP-010](requirements.md) | Apply registered paired scoring without dropping failures | `data-pipeline/pipeline/coupled_analysis.py`; `tests/coupled/test_coupled_analysis.py` |

## Exact requirement gates

Each requirement retains its own positive/behavioral gate and its distinct hostile check in [validation](validation.md). This table is an interface-to-proof map; it makes no claim that an unobserved command passed.

| Requirement | Dependency unit | Required gate from the current specification | Current convergence boundary |
|---|---|---|---|
| [CP-001](requirements.md) | P1 | `tests/coupled/test_coupled_contract.py::test_batch_producer_consumer_roundtrip` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CP-002](requirements.md) | P1 | `tests/coupled/test_coupled_contract.py::test_adversarial_malformed_batch_rejects_before_native_setup` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CP-003](requirements.md) | P2 | `tests/coupled/test_coupled_correctness.py::test_adversarial_synthetic_forecasts_have_same_semantics_and_native_oracle_accuracy` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CP-004](requirements.md) | P2 | `tests/coupled/test_coupled_correctness.py::test_adversarial_independent_gate_rejects_joint_dual_and_raw_stationarity_counterexamples` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CP-005](requirements.md) | P1 | `tests/coupled/test_coupled_requirements.py::test_exact_separate_profile_matches_all_protocol_pins`, `tests/coupled/test_coupled_requirements.py::test_adversarial_dependency_drift_or_unpinned_options_are_rejected` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CP-006](requirements.md) | P4 | `tests/coupled/test_coupled_export.py::test_complete_downstream_replay_and_exact_csv` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CP-007](requirements.md) | P4 | `tests/coupled/test_coupled_export.py::test_adversarial_replay_rejects_tampering_even_when_outer_checksums_are_recomputed` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CP-008](requirements.md) | P5 | `tests/coupled/test_coupled_analysis.py::test_fastest_registered_baseline_and_seed_bootstrap` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CP-009](requirements.md) | P5 | `tests/coupled/test_coupled_analysis.py::test_adversarial_bad_baseline_cannot_disappear_or_improve_the_primary_endpoint` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CP-010](requirements.md) | P5 | `tests/coupled/test_coupled_analysis.py::test_predeclared_incompatibility_is_visible_and_warmups_do_not_enter_estimate`, `tests/coupled/test_coupled_analysis.py::test_adversarial_spoofed_compatibility_or_partial_population_cannot_qualify` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CP-011](requirements.md) | P1 | `tests/coupled/test_coupled_registration_and_workers.py::test_registered_scientific_sources_remain_unchanged`, `tests/coupled/test_coupled_registration_and_workers.py::test_adversarial_registration_refuses_changed_authorities` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CP-012](requirements.md) | P3 | `tests/coupled/test_coupled_registration_and_workers.py::test_adversarial_supervisor_refuses_limits_and_incomplete_output` | Implementation mapped; current gate execution is a separate acceptance obligation. |

## Current convergence

The offline vertical has production and consumer controls, but its held-out performance criterion is not established. Failure preservation, full source identity and actual export replay remain required even when unit fixtures pass. The lane has no declared coupled browser replay adapter; publication does not change that missing-data boundary.

The design in [design.md](design.md), all current requirement rows and their validation rows are explicit. Structural document checks verify these links and identifiers. They do not substitute for executing the functional gates or for independently reviewing a changed numerical or visual result.
