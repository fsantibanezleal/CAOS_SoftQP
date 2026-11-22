# Dependency graph and convergence: repository

External runtime admission and source identity precede generation; complete staged validation precedes explicit promotion; development process ownership depends on initialized matching inputs. This graph follows the existing repository workflow rather than creating an execution plan inside the product.

## Dependency sequence

| Unit | Requires | Requirements | Implementation responsibility | Production and test files |
|---|---|---|---|---|
| R1 | None | [RP-011](requirements.md), [RP-012](requirements.md), [RP-017](requirements.md), [RP-021](requirements.md), [RP-025](requirements.md), [RP-029](requirements.md) | Check prerequisites and admit exact external runtime namespaces | `scripts/local/workflow.py`; `scripts/local/workflow.json`; `tests/test_local_bootstrap.py`; `tests/test_bootstrap_admission.py` |
| R2 | R1 | [RP-013](requirements.md), [RP-018](requirements.md), [RP-019](requirements.md), [RP-026](requirements.md), [RP-030](requirements.md), [RP-031](requirements.md) | Generate an external stage and verify the complete authored matrix | `scripts/local/softqp_adapter.py`; `scripts/local/producer_bridge.py`; `tests/test_local_softqp_admission.py` |
| R3 | R2 | [RP-014](requirements.md), [RP-020](requirements.md), [RP-028](requirements.md) | Promote one immutable receipt with owned rollback and preserved recovery | `scripts/local/workflow.py`; `tests/test_bootstrap_admission.py`; `tests/test_bootstrap_regressions.py` |
| R4 | R1, R2 | [RP-015](requirements.md), [RP-022](requirements.md), [RP-023](requirements.md), [RP-027](requirements.md) | Launch initialized dev children with scoped environment and cleanup | `scripts/local/workflow.py`; `frontend/scripts/copy-data.mjs`; `tests/test_bootstrap_regressions.py` |
| R5 | R1, R3, R4 | [RP-016](requirements.md), [RP-024](requirements.md), [RP-032](requirements.md) | Preserve shell failure/mode behavior and attributed redistribution | `scripts/setup.ps1`; `scripts/setup.sh`; `scripts/local/README.md`; `LICENSES.md`; `tests/test_attribution.py` |

## Exact requirement gates

Each requirement retains its own positive/behavioral gate and its distinct hostile check in [validation](validation.md). This table is an interface-to-proof map; it makes no claim that an unobserved command passed.

| Requirement | Dependency unit | Required gate from the current specification | Current convergence boundary |
|---|---|---|---|
| [RP-011](requirements.md) | R1 | `tests/test_local_bootstrap.py::test_adversarial_prerequisites_are_check_only` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-012](requirements.md) | R1 | `tests/test_local_bootstrap.py::test_adversarial_init_preserves_env_and_installs_by_fingerprint` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-013](requirements.md) | R2 | `tests/test_local_bootstrap.py::test_adversarial_generation_is_sandboxed_and_absence_is_actionable` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-014](requirements.md) | R3 | `tests/test_local_bootstrap.py::test_adversarial_release_rejects_mixed_partial_and_rolls_back` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-015](requirements.md) | R4 | `tests/test_local_bootstrap.py::test_adversarial_dev_supervises_api_and_frontend` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-016](requirements.md) | R5 | `tests/test_local_bootstrap.py::test_adversarial_shell_entrypoints_propagate_failure` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-017](requirements.md) | R1 | `tests/test_bootstrap_regressions.py::test_adversarial_receipt_current_contract_and_recursive_pins` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-018](requirements.md) | R2 | `tests/test_bootstrap_regressions.py::test_adversarial_actual_readiness_inventory` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-019](requirements.md) | R2 | `tests/test_bootstrap_regressions.py::test_adversarial_actual_template_registry` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-020](requirements.md) | R3 | `tests/test_bootstrap_regressions.py::test_adversarial_rollback_continues_and_preserves_recovery` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-021](requirements.md) | R1 | `tests/test_bootstrap_regressions.py::test_adversarial_dev_python_initialization_admission` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-022](requirements.md) | R4 | `tests/test_bootstrap_regressions.py::test_adversarial_exited_parent_descendant_ownership` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-023](requirements.md) | R4 | `tests/test_bootstrap_regressions.py::test_adversarial_external_runtime_alias_and_cleanup` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-024](requirements.md) | R5 | `tests/test_bootstrap_regressions.py::test_adversarial_tracked_shell_modes` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-025](requirements.md) | R1 | `tests/test_bootstrap_regressions.py::test_adversarial_locked_node_engines` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-026](requirements.md) | R2 | `tests/test_local_softqp_admission.py::test_adversarial_rehashed_incomplete_inventory_is_refused`, `tests/test_bootstrap_regressions.py::test_adversarial_real_product_generation_admission` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-027](requirements.md) | R4 | `tests/test_bootstrap_regressions.py::test_adversarial_frontend_environment_isolation` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-028](requirements.md) | R3 | `tests/test_bootstrap_admission.py::test_adversarial_validator_cannot_change_accepted_identity`, `tests/test_bootstrap_admission.py::test_adversarial_copy_and_install_are_bound_to_original_receipt`, `tests/test_bootstrap_admission.py::test_adversarial_receipt_is_one_parse_and_hash_snapshot` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-029](requirements.md) | R1 | `tests/test_bootstrap_admission.py::test_adversarial_external_environment_policy_refuses_internal_targets`, `tests/test_bootstrap_admission.py::test_adversarial_external_namespace_is_a_safe_required_component`, `tests/test_bootstrap_admission.py::test_adversarial_external_alias_containment`, `tests/test_bootstrap_admission.py::test_adversarial_initializer_enforces_external_location_before_writes`, `tests/test_bootstrap_admission.py::test_adversarial_external_non_directory_target_refuses_before_writes`, `tests/test_bootstrap_admission.py::test_adversarial_external_defaults_and_instantiation_are_bound` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-030](requirements.md) | R2 | `tests/test_local_softqp_admission.py::test_complete_authored_inventory_is_admitted`, `tests/test_local_softqp_admission.py::test_adversarial_rehashed_incomplete_inventory_is_refused` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-031](requirements.md) | R2 | `tests/test_local_softqp_admission.py::test_adversarial_input_settings_and_objective_parity`, `tests/test_local_softqp_admission.py::test_validated_objective_baselines_preserve_reviewed_sources` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [RP-032](requirements.md) | R5 | `tests/test_attribution.py::test_adversarial_third_party_credit_and_redistribution` | Implementation mapped; current gate execution is a separate acceptance obligation. |

## Current convergence

The numbered entrypoints, standard-library supervisor and product adapter exist. A validated stage is not a deployed release, and rehashing altered metadata cannot replace its admitted snapshot. Real authored-case generation, actual frontend environment isolation and controlled failure/rollback checks remain distinct from documentation presence. Historical SDK environments and frozen studies are not overwritten by ordinary initialization.

The design in [design.md](design.md), all current requirement rows and their validation rows are explicit. Structural document checks verify these links and identifiers. They do not substitute for executing the functional gates or for independently reviewing a changed numerical or visual result.
