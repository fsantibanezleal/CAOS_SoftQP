# Adversarial validation: soft-QP pipeline

| requirement | adversarial check | gate |
|---|---|---|
| SQ-001 | A duplicate ID is planted in the catalog and the bake must stop before any result is accepted. | `tests/adversarial/test_softqp_boundary.py::test_adversarial_duplicate_case_id_blocks_bake` |
| SQ-002 | An asymmetric case must be explicitly incompatible with the symmetric reference, never silently solved with different costs. | `tests/adversarial/test_softqp_boundary.py::test_adversarial_semantics_mismatch_is_incompatible` |
| SQ-003 | Unequal weights are planted inside a shared penalty group and the native solver must reject it. | `tests/adversarial/test_softqp_boundary.py::test_adversarial_inconsistent_group_weights_fail_native` |
| SQ-004 | An exported byte is changed without updating the digest; inventory verification must reject the changed file. | `tests/adversarial/test_softqp_boundary.py::test_adversarial_changed_artifact_byte_breaks_inventory` |
