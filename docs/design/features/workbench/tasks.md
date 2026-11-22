# Dependency graph and convergence: workbench

A deterministic mathematical case and its original-space result precede checksummed loading. Selected case/method/unit then drive every visible view, with direct-route and measured-layout obligations at the built-site boundary. This graph reconciles the existing scientific workbench rather than defining a new generic example.

## Dependency sequence

| Unit | Requires | Requirements | Implementation responsibility | Production and test files |
|---|---|---|---|---|
| E1 | None | [EX-001](requirements.md), [EX-002](requirements.md), [EX-004](requirements.md) | Admit deterministic authored input and declared numerical ranges | `data-pipeline/pipeline/softqp_cases.py`; `tests/test_contract.py`; `tests/test_expect.py`; `tests/test_pipeline_smoke.py` |
| E2 | E1 | [EX-003](requirements.md), [EX-005](requirements.md), [EX-008](requirements.md) | Protect canonical artifacts and enforce actual typed JSON transport | `tests/conftest.py`; `frontend/src/lib/softqp.ts`; `frontend/src/api/artifacts.ts` |
| E3 | E2 | [EX-011](requirements.md) | Bind the selected case and controls to every workbench view | `frontend/src/workbench/Workbench.tsx`; `frontend/scripts/gate.mjs` |
| E4 | E2, E3 | [EX-009](requirements.md), [EX-010](requirements.md), [EX-012](requirements.md) | Materialize direct routes, measure real drawn space and preserve version identity | `frontend/scripts/materialize-routes.mjs`; `frontend/scripts/gate.mjs`; `scripts/check_version_coherence.py` |

## Exact requirement gates

Each requirement retains its own positive/behavioral gate and its distinct hostile check in [validation](validation.md). This table is an interface-to-proof map; it makes no claim that an unobserved command passed.

| Requirement | Dependency unit | Required gate from the current specification | Current convergence boundary |
|---|---|---|---|
| [EX-001](requirements.md) | E1 | `tests/test_expect.py::test_a_value_outside_its_range_is_named` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [EX-002](requirements.md) | E1 | `tests/test_pipeline_smoke.py::test_adversarial_same_seed_bakes_identical_bytes_and_a_changed_byte_of_equal_size_is_seen` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [EX-003](requirements.md) | E2 | `tests/conftest.py` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [EX-004](requirements.md) | E1 | `tests/test_contract.py::test_adversarial_bad_rows_rejected_not_coerced` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [EX-005](requirements.md) | E2 | `frontend/src/lib/contract.test.ts::validates the index, manifest, result and byte inventory` (and, per case, `manifest and trace conform`, over the bake and the provider tree) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [EX-008](requirements.md) | E2 | `frontend/src/api/artifacts.test.ts::adversarial: refuses an HTML answer (the host fallback for a missing file)` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [EX-009](requirements.md) | E4 | `frontend/scripts/materialize-routes.mjs`, measured by `frontend/scripts/gate.mjs` (G4) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [EX-010](requirements.md) | E4 | `frontend/scripts/gate.mjs` (G6) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [EX-011](requirements.md) | E3 | `frontend/scripts/gate.mjs` (G9) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [EX-012](requirements.md) | E4 | `scripts/check_version_coherence.py` | Implementation mapped; current gate execution is a separate acceptance obligation. |

## Current convergence

The case pipeline, typed reader and shared workbench are connected in production source. Selection-key propagation, actual rendered values and current stage dimensions require the browser gate and direct interaction checks, not only a matching attribute. EX-010 records the older half-viewport floor; passing it alone does not satisfy the current stronger stage/story bar. Timing fields are not claimed byte-deterministic.

The design in [design.md](design.md), all current requirement rows and their validation rows are explicit. Structural document checks verify these links and identifiers. They do not substitute for executing the functional gates or for independently reviewing a changed numerical or visual result.
