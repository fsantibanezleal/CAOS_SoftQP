# Dependency graph and convergence: coupled lessons

A small teaching calculation depends on a separately admitted SDK runtime, not on a browser adapter or a rerun of the registered computation. These dependencies describe the implemented bridge and current lesson obligations, retrospectively.

## Dependency sequence

| Unit | Requires | Requirements | Implementation responsibility | Production and test files |
|---|---|---|---|---|
| L1 | None | [CL-001](requirements.md) | Admit the explicit external runtime, request and bounded owned worker | `data-pipeline/pipeline/coupled_lessons.py`; `data-pipeline/pipeline/lesson_process.py` |
| L2 | L1 | [CL-002](requirements.md) | Run native, compact epigraph and row-split paths with original metrics | `data-pipeline/pipeline/coupled_lesson_worker.py`; `docs/contracts/schemas/softqp-coupled-lesson.schema.json` |
| L3 | L2 | [CL-003](requirements.md) | Exercise directional reciprocal row-unit covariance | `tests/test_coupled_lessons.py` |
| L4 | L2, L3 | [CL-004](requirements.md), [CL-005](requirements.md) | Teach the method in both languages and distinguish accepted evidence | `notebooks/en/01-soft-constraint-decisions/05-directional-group-peaks.ipynb`; `notebooks/es/01-soft-constraint-decisions/05-directional-group-peaks.ipynb`; `docs/teaching/coupled/accepted-summary.json` |

## Exact requirement gates

Each requirement retains its own positive/behavioral gate and its distinct hostile check in [validation](validation.md). This table is an interface-to-proof map; it makes no claim that an unobserved command passed.

| Requirement | Dependency unit | Required gate from the current specification | Current convergence boundary |
|---|---|---|---|
| [CL-001](requirements.md) | L1 | `tests/test_coupled_lessons.py::test_adversarial_external_lesson_boundary` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CL-002](requirements.md) | L2 | `tests/test_coupled_lessons.py::test_adversarial_real_methods_share_the_original_objective` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CL-003](requirements.md) | L3 | `tests/test_coupled_lessons.py::test_adversarial_directional_row_unit_covariance` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CL-004](requirements.md) | L4 | `tests/test_coupled_lessons.py::test_adversarial_coupled_curriculum_and_evidence_identity` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [CL-005](requirements.md) | L4 | `tests/test_coupled_lessons.py::test_adversarial_coupled_curriculum_and_evidence_identity` | Implementation mapped; current gate execution is a separate acceptance obligation. |

## Current convergence

The bridge, schema and mirrored lessons exist. Runtime source fingerprints, bounded cleanup and actual numerical calls need their behavioral controls; a schema example alone is insufficient. The current notebook content floors and independent per-figure review add to the older CL-004 minimum. The negative registered criterion and archived population are retained, and no new campaign is implied.

The design in [design.md](design.md), all current requirement rows and their validation rows are explicit. Structural document checks verify these links and identifiers. They do not substitute for executing the functional gates or for independently reviewing a changed numerical or visual result.
