# Dependency graph and convergence: contracts

Schema admission precedes numerical production, and production precedes availability and serving. The catalog fixes the interface before a fixture or a real source is selected. This graph reconciles the existing implementation and its validation responsibilities; it is not a session backlog.

## Dependency sequence

| Unit | Requires | Requirements | Implementation responsibility | Production and test files |
|---|---|---|---|---|
| C1 | None | [CT-001](requirements.md), [CT-002](requirements.md), [CT-003](requirements.md), [CT-004](requirements.md) | Define the original-space schemas and semantic sparse decoder | `docs/contracts/catalog.md`; `data-pipeline/pipeline/io/contract.py`; `tests/contracts/test_documents.py`; `tests/test_contract.py` |
| C2 | C1 | [CT-005](requirements.md), [CT-006](requirements.md), [CT-007](requirements.md) | Generate and validate both web and API document types | `frontend/scripts/gen-contract-types.mjs`; `frontend/src/lib/softqp.ts`; `frontend/src/lib/contract.gen.ts` |
| C3 | C1 | [CT-009](requirements.md), [CT-010](requirements.md), [CT-011](requirements.md), [CT-014](requirements.md), [CT-015](requirements.md), [CT-016](requirements.md), [CT-026](requirements.md), [CT-039](requirements.md) | Compute actual selected-root readiness without numerical imports | `data-pipeline/pipeline/core/readiness.py`; `tests/contracts/test_readiness.py` |
| C4 | C2, C3 | [CT-019](requirements.md), [CT-020](requirements.md), [CT-021](requirements.md), [CT-027](requirements.md), [CT-028](requirements.md) | Serve only declared read-only documents and typed failures | `app/main.py`; `tests/contracts/test_api.py` |
| C5 | C2, C3 | [CT-022](requirements.md), [CT-023](requirements.md), [CT-024](requirements.md) | Render only the consuming view state and prevent forbidden fetches | `frontend/src/readiness/readiness.ts`; `frontend/src/workbench/Workbench.readiness.test.tsx` |
| C6 | C1 | [CT-034](requirements.md), [CT-035](requirements.md), [CT-036](requirements.md), [CT-037](requirements.md), [CT-038](requirements.md) | Enforce document-path declarations and repository admission independently | `scripts/check_contracts.py`; `scripts/check_base_integrity.py`; `scripts/check_content_standards.py` |

## Exact requirement gates

Each requirement retains its own positive/behavioral gate and its distinct hostile check in [validation](validation.md). This table is an interface-to-proof map; it makes no claim that an unobserved command passed.

| Requirement | Dependency unit | Required gate from the current specification | Current convergence boundary |
|---|---|---|---|
| [CT-001](requirements.md) | C1 | `tests/contracts/test_documents.py::test_manifests_validate` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-002](requirements.md) | C1 | `tests/contracts/test_documents.py::test_fixture_tree_validates` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-003](requirements.md) | C1 | `tests/contracts/test_documents.py::test_adversarial_drifted_documents_are_rejected` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-004](requirements.md) | C1 | `tests/test_contract.py::test_adversarial_bad_rows_rejected_not_coerced` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-005](requirements.md) | C2 | `frontend/scripts/gen-contract-types.mjs`, run by `npm run build` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-006](requirements.md) | C2 | `frontend/src/lib/contract.test.ts::validates readiness and rejects a changed schema identifier` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-007](requirements.md) | C2 | `frontend/src/lib/api.contract.test.ts::200 bodies` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-009](requirements.md) | C3 | `tests/contracts/test_readiness.py::test_adversarial_state_partial_manifests` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-010](requirements.md) | C3 | `tests/contracts/test_readiness.py::test_adversarial_state_stale` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-011](requirements.md) | C3 | `tests/contracts/test_readiness.py::test_adversarial_state_provider_through_a_catalog_copy` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-014](requirements.md) | C3 | `tests/contracts/test_readiness.py::test_adversarial_state_missing_without_an_index` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-015](requirements.md) | C3 | `tests/contracts/test_readiness.py::test_adversarial_check_readiness_fails_on_a_changed_catalog` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-016](requirements.md) | C3 | `tests/contracts/test_readiness.py::test_adversarial_check_readiness_runs_without_numpy` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-019](requirements.md) | C4 | `tests/contracts/test_api.py::test_responses_match_the_openapi_document` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-020](requirements.md) | C4 | `tests/contracts/test_api.py::test_adversarial_503_when_documents_are_absent` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-021](requirements.md) | C4 | `tests/contracts/test_api.py::test_adversarial_404_bodies_and_nothing_outside_the_root` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-022](requirements.md) | C5 | `frontend/src/readiness/readiness.test.ts::adversarial: order: missing, partial, training, provider, stale, available; the most severe wins`, `frontend/src/workbench/Workbench.readiness.test.tsx::adversarial: actual Workbench shows the recorded stale reason and keeps unrelated rows separate` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-023](requirements.md) | C5 | `frontend/src/readiness/readiness.test.ts::a fetch that fails resolves to null, names the cause on the console, and is asked for once` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-024](requirements.md) | C5 | `frontend/src/readiness/readiness.test.ts::adversarial: loadCase rejects with ArtifactUnavailable naming the path and the reason, and never fetches the trace` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-026](requirements.md) | C3 | `tests/contracts/test_readiness.py::test_adversarial_check_readiness_reports_an_unknown_status` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-027](requirements.md) | C4 | `tests/contracts/test_api.py::test_every_document_under_the_root_is_served_as_declared_or_404` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-028](requirements.md) | C4 | `tests/contracts/test_api.py::test_adversarial_an_unreadable_index_is_a_503` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-034](requirements.md) | C6 | `tests/contracts/test_check_contracts.py::test_a_catalog_without_the_column_names_it_and_the_release` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-035](requirements.md) | C6 | `tests/adversarial/test_base_integrity_plants.py::test_a_model_file_named_by_no_row_fails` (and `tests/adversarial/test_fix_round_0_09_0.py::test_a_declared_heavy_parquet_is_refused`, `tests/adversarial/test_fix_round_0_09_0.py::test_a_declared_venv_file_is_refused`, `tests/adversarial/test_fix_round_0_09_0.py::test_a_declared_npy_array_is_not_admitted_as_a_model_file`) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-036](requirements.md) | C6 | `tests/adversarial/test_base_integrity_plants.py::test_a_declared_model_file_over_five_mb_fails` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-037](requirements.md) | C6 | `tests/adversarial/test_base_integrity_plants.py::test_an_allow_listed_notice_passes_and_an_edited_one_fails`, `tests/adversarial/test_base_integrity_plants.py::test_an_allow_listed_path_that_does_not_exist_fails` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-038](requirements.md) | C6 | `tests/adversarial/test_base_integrity_plants.py::test_a_real_env_file_tracked_fails`, `tests/adversarial/test_base_integrity_plants.py::test_a_machine_path_in_a_source_fails`, `tests/adversarial/test_fix_round_0_09_0.py::test_a_machine_path_inside_a_tracked_binary_fails` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CT-039](requirements.md) | C3 | `tests/contracts/test_readiness.py::test_adversarial_coupled_examples_do_not_establish_deployed_evidence`, `tests/contracts/test_readiness.py::test_adversarial_undeclared_coupled_payload_cannot_become_available`, `tests/contracts/test_readiness.py::test_adversarial_fixture_coupled_rows_remain_labelled_providers` | Implementation mapped; current gate execution is a separate acceptance obligation. |

## Current convergence

All named boundaries have concrete production paths and hostile controls. Current result files can still be stale or unavailable by declared design; passing the catalog check cannot upgrade their states. Functional acceptance requires the named Python/TypeScript tests and the actual consumer paths, with malformed, missing and rehashed controls retained.

The design in [design.md](design.md), all current requirement rows and their validation rows are explicit. Structural document checks verify these links and identifiers. They do not substitute for executing the functional gates or for independently reviewing a changed numerical or visual result.
