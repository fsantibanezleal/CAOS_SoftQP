# Requirements: soft-QP formulation and artifact pipeline

| ID | Requirement | Gate |
|---|---|---|
| SQ-001 | THE pipeline SHALL enumerate all fifteen declared case IDs once. | `tests/test_softqp_matrix.py::test_case_catalog_covers_fifteen_declared_ids` |
| SQ-002 | WHEN compatible scalar formulations run, THE pipeline SHALL reproduce the same original-space objective within 1e-6. | `tests/test_softqp_matrix.py::test_scalar_methods_share_objective_and_hard_policy` |
| SQ-003 | WHEN the grouped reference runs, THE native and lifted objectives SHALL agree within 1e-6. | `tests/test_softqp_matrix.py::test_grouped_reference_matches_explicit_lift` |
| SQ-004 | THE pipeline SHALL export a SHA-256 inventory of every case result to the explicitly supplied output root. | `tests/test_softqp_matrix.py::test_bake_writes_hashed_inventory_outside_committed_data` |
