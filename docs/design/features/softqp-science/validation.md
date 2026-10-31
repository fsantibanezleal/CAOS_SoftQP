# Adversarial validation: soft-QP pipeline

| requirement | adversarial check | gate |
|---|---|---|
| SQ-001 | Compare the exact set and order, so missing, repeated or renamed cases fail. | `tests/test_softqp_matrix.py::test_case_catalog_covers_fifteen_declared_ids` |
| SQ-002 | Solve independently lifted and native formulations, then compare recomputed original-space objectives rather than trusting solver-reported cost. | `tests/test_softqp_matrix.py::test_scalar_methods_share_objective_and_hard_policy` |
| SQ-003 | Compare the grouped native proximal result with the independently lifted QP epigraph. | `tests/test_softqp_matrix.py::test_grouped_reference_matches_explicit_lift` |
| SQ-004 | Recompute hashes from actual bytes in a test-only directory; any inventory drift fails. | `tests/test_softqp_matrix.py::test_bake_writes_hashed_inventory_outside_committed_data` |
