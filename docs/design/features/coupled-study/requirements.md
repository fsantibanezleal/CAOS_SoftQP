# Requirements: directional coupled-penalty computation

The registered computation is a separate offline lane using the public SoftQP
0.2.0 profile. These requirements make its already implemented boundaries explicit;
they do not revise the frozen protocol, source registration or acceptance criterion.

| ID | Requirement | Gate |
|---|---|---|
| CP-001 | THE batch producer and consumer SHALL preserve the sparse original problem, directional group prices, physical units and every forecast through an encode/decode round trip. | `tests/coupled/test_coupled_contract.py::test_batch_producer_consumer_roundtrip` |
| CP-002 | IF sparse indices, dimensions, directional scales, group ownership, finite-side patterns, units or update values are malformed, THEN THE consumer SHALL reject the batch before native setup. | `tests/coupled/test_coupled_contract.py::test_adversarial_malformed_batch_rejects_before_native_setup` |
| CP-003 | THE native workspace and independent epigraph comparator SHALL solve the same declared sparse and thermal objectives across the supported curvature and peak-price families, while preserving hard rows and fixed matrices. | `tests/coupled/test_coupled_correctness.py::test_adversarial_synthetic_forecasts_have_same_semantics_and_native_oracle_accuracy` |
| CP-004 | THE independent numerical consumer SHALL reject invalid joint dual budgets, excessive raw stationarity, cancelling signed gaps and nonfinite metrics instead of accepting a repaired or aggregate residual alone. | `tests/coupled/test_coupled_correctness.py::test_adversarial_independent_gate_rejects_joint_dual_and_raw_stationarity_counterexamples` |
| CP-005 | THE study environment SHALL match every registered public-package pin and SHALL reject dependency drift and unpinned requirement options. | `tests/coupled/test_coupled_requirements.py::test_exact_separate_profile_matches_all_protocol_pins`, `tests/coupled/test_coupled_requirements.py::test_adversarial_dependency_drift_or_unpinned_options_are_rejected` |
| CP-006 | THE experiment consumer SHALL reconstruct a complete exported observation population and its exact CSV from the actual producer journals, preserving the declared source and input identity. | `tests/coupled/test_coupled_export.py::test_complete_downstream_replay_and_exact_csv` |
| CP-007 | IF raw bytes, source identity, canonical inputs, dataset summaries, frame metrics, backend labels, row coverage or CSV content differ, THEN THE experiment consumer SHALL reject the export even when an attacker recomputes outer checksums. | `tests/coupled/test_coupled_export.py::test_adversarial_replay_rejects_tampering_even_when_outer_checksums_are_recomputed` |
| CP-008 | THE primary analysis SHALL select the fastest registered compatible baseline, retain the complete registered population and resample whole seed clusters. | `tests/coupled/test_coupled_analysis.py::test_fastest_registered_baseline_and_seed_bootstrap` |
| CP-009 | IF a compatible observation is missing, unsuccessful or has an invalid elapsed time, THEN THE analysis SHALL retain its failed pair with the prescribed score and SHALL refuse scientific qualification. | `tests/coupled/test_coupled_analysis.py::test_adversarial_bad_baseline_cannot_disappear_or_improve_the_primary_endpoint` |
| CP-010 | THE analysis SHALL exclude warmups from inference, preserve genuine declared incompatibilities, and reject spoofed compatibility or a partial primary inventory. | `tests/coupled/test_coupled_analysis.py::test_predeclared_incompatibility_is_visible_and_warmups_do_not_enter_estimate`, `tests/coupled/test_coupled_analysis.py::test_adversarial_spoofed_compatibility_or_partial_population_cannot_qualify` |

| CP-011 | THE execution boundary SHALL require the exact registered protocol, source and independent acceptance, rejecting changed, dirty or untracked protected authorities before scientific work. | `tests/coupled/test_coupled_registration_and_workers.py::test_registered_scientific_sources_remain_unchanged`, `tests/coupled/test_coupled_registration_and_workers.py::test_adversarial_registration_refuses_changed_authorities` |
| CP-012 | IF a worker exceeds the registered wall or memory limit, emits oversized or malformed output, or supplies an incomplete oracle, THEN THE supervisor SHALL return a failure without a completed timing, close its owned worker and preserve the failed observation. | `tests/coupled/test_coupled_registration_and_workers.py::test_adversarial_supervisor_refuses_limits_and_incomplete_output` |

Complete real-study replay and independent
mathematical review are additional acceptance obligations. The tests above exercise
their named boundaries; they are not a substitute for reviewing the complete study
or its public manuscript. The heldout performance criterion is not established.
