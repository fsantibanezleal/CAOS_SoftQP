# Requirements: soft-QP formulation and artifact pipeline

| ID | Requirement | Gate |
|---|---|---|
| SQ-001 | THE pipeline SHALL enumerate all fifteen declared case IDs once. | `tests/test_softqp_matrix.py::test_case_catalog_covers_fifteen_declared_ids` |
| SQ-002 | WHEN compatible scalar formulations run, THE pipeline SHALL reproduce the same original-space objective within 1e-6. | `tests/test_softqp_matrix.py::test_scalar_methods_share_objective_and_hard_policy` |
| SQ-003 | WHEN the grouped reference runs, THE native and lifted objectives SHALL agree within 1e-6. | `tests/test_softqp_matrix.py::test_grouped_reference_matches_explicit_lift` |
| SQ-004 | THE pipeline SHALL export a SHA256 inventory of every case result to the explicitly supplied output root. | `tests/test_softqp_matrix.py::test_bake_writes_hashed_inventory_outside_committed_data` |
| SQ-005 | WHEN bounded side-cost edits are executed locally, THE product SHALL compute a changed native optimum with preserved hard policy. | `tests/test_softqp_requests.py::test_local_request_recomputes_a_changed_optimum` |
| SQ-006 | IF the request references a stale base digest or coupled penalties, THEN THE executor SHALL refuse the request. | `tests/test_softqp_requests.py::test_adversarial_stale_and_grouped_requests_are_rejected` |
| SQ-007 | WHEN a local result is imported, THE reader SHALL verify declared inputs, original objective and side violations before rendering it. | `frontend/src/lib/softqp.local.test.ts::accepts the actual native producer and independently verifies original costs` |
| SQ-008 | THE stream exporter SHALL preserve all 32 common-input frames and their paired cold/warm method states. | `tests/test_softqp_stream.py::test_c12_complete_pairing_and_accuracy` |
| SQ-009 | THE experimental exporter SHALL validate the complete instance/method/repetition matrix and recompute its summaries from raw trials. | `tests/test_experiment_export.py::test_experimental_exports_and_provider` |
| SQ-010 | THE numerical evaluator SHALL check original stationarity and the interval-penalty proximal relation after recovering solver duals. | `tests/test_softqp_optimality.py::test_original_kkt_on_solver_and_scaled_rows` |
| SQ-011 | THE physical predictor SHALL preserve the declared double-integrator dynamics without clipping supplied controls. | `tests/test_softqp_control.py::test_predictor_retains_input_and_physical_dynamics` |
