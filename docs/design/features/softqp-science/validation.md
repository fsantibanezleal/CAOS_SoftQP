# Adversarial validation: soft-QP pipeline

| requirement | adversarial check | gate |
|---|---|---|
| SQ-001 | A duplicate ID is planted in the catalog and the bake must stop before any result is accepted. | `tests/scientific/test_softqp_boundary.py::test_adversarial_duplicate_case_id_blocks_bake` |
| SQ-002 | An asymmetric case must be explicitly incompatible with the symmetric reference, never silently solved with different costs. | `tests/scientific/test_softqp_boundary.py::test_adversarial_semantics_mismatch_is_incompatible` |
| SQ-003 | Unequal weights are planted inside a shared penalty group and the native solver must reject it. | `tests/scientific/test_softqp_boundary.py::test_adversarial_inconsistent_group_weights_fail_native` |
| SQ-004 | An exported byte is changed without updating the digest; inventory verification must reject the changed file. | `tests/scientific/test_softqp_boundary.py::test_adversarial_changed_artifact_byte_breaks_inventory` |
| SQ-005 | Boolean, zero and over-budget cost multipliers are rejected before optimization. | `tests/test_softqp_requests.py::test_adversarial_request_rejects_unbounded_or_invalid_edits` |
| SQ-006 | A zero digest and a group-penalty request must be refused instead of silently changing the source or formulation. | `tests/test_softqp_requests.py::test_adversarial_stale_and_grouped_requests_are_rejected` |
| SQ-007 | Altered request, matrices, hard-row policy, cost and violation vectors are independently rejected. | `frontend/src/lib/softqp.local.test.ts::adversarial: rejects altered request, problem, row policy and computed costs` |
| SQ-008 | Invalid vector updates or an unpinned stream engine are refused; hard dynamics remain the declared model. | `tests/test_softqp_stream.py::test_adversarial_stream_refuses_an_unpinned_engine` |
| SQ-009 | A raw observation is removed and its digest is updated; the denominator check must still fail. | `tests/test_experiment_export.py::test_adversarial_export_rejects_missing_raw_trial` |
| SQ-010 | A stationary but incorrectly unpriced solution must have a positive interval-penalty defect. | `tests/test_softqp_optimality.py::test_adversarial_stationarity_alone_does_not_certify_soft_optimum` |
| SQ-011 | Nonfinite or malformed physical prediction inputs must be rejected. | `tests/test_softqp_control.py::test_adversarial_predictor_rejects_invalid_inputs` |
