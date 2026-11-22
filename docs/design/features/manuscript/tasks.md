# Dependency graph and convergence: manuscript

Document identity and evidence authority precede asset generation; content and compilation precede independent publication admission. The technical report and research paper remain separate throughout. This graph records current architecture without assigning these documents an invented earlier date.

## Dependency sequence

| Unit | Requires | Requirements | Implementation responsibility | Production and test files |
|---|---|---|---|---|
| M1 | None | [MS-001](requirements.md), [MS-002](requirements.md), [MS-003](requirements.md) | Define separate native article sources, base and complete identity | `manuscripts/soft-constraint-study/main.tex`; `manuscripts/coupled-peak-study/main.tex` |
| M2 | M1 | [MS-004](requirements.md), [MS-005](requirements.md) | Generate literal tables/vector assets from both immutable authorities with the shared producer; verify or refresh macros through the per-document entrypoints before compilation | `manuscripts/shared/generate_assets.py`; `manuscripts/soft-constraint-study/build.py`; `manuscripts/coupled-peak-study/build.py`; `scripts/build_manuscript.py` |
| M3 | M1, M2 | [MS-007](requirements.md), [MS-008](requirements.md) | Measure complete method, contract, theory and experiment coverage | `scripts/manuscript_content_bar.py`; `manuscripts/soft-constraint-study/coverage.json`; `manuscripts/coupled-peak-study/coverage.json` |
| M4 | M2, M3 | [MS-006](requirements.md), [MS-009](requirements.md) | Compile cleanly while binding recursive source and driver identities | `scripts/build_manuscript.py`; `tests/test_manuscript_sources.py` |
| M5 | M4 | [MS-010](requirements.md) | Require independently anchored final-source/PDF/publication acceptance | `scripts/publication_acceptance.py`; `tests/test_manuscript_sources.py` |

## Exact requirement gates

Each requirement retains its own positive/behavioral gate and its distinct hostile check in [validation](validation.md). This table is an interface-to-proof map; it makes no claim that an unobserved command passed.

| Requirement | Dependency unit | Required gate from the current specification | Current convergence boundary |
|---|---|---|---|
| [MS-001](requirements.md) | M1 | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_native_article_source` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MS-002](requirements.md) | M1 | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_standard_front_matter` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MS-003](requirements.md) | M1 | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_author_and_running_identity` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MS-004](requirements.md) | M2 | `tests/test_manuscript_sources.py::test_adversarial_manuscript_refuses_raster_equations` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MS-005](requirements.md) | M2 | `tests/test_manuscript_sources.py::test_adversarial_manuscript_results_match_accepted_evidence` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MS-006](requirements.md) | M4 | `tests/test_manuscript_sources.py::test_adversarial_manuscript_build_uses_latex` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MS-007](requirements.md) | M3 | `tests/test_manuscript_sources.py::test_adversarial_manuscripts_meet_current_content_bar` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MS-008](requirements.md) | M3 | `tests/test_manuscript_sources.py::test_adversarial_manuscripts_meet_current_content_bar` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MS-009](requirements.md) | M4 | `tests/test_manuscript_sources.py::test_adversarial_manuscript_source_change_during_build_is_refused` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MS-010](requirements.md) | M5 | `tests/test_manuscript_sources.py::test_adversarial_publication_requires_independent_acceptance` | Implementation mapped; current gate execution is a separate acceptance obligation. |

## Current convergence

Both native sources, coverage maps and compiler/admission paths exist. Measured content, hostile source mutation and independent page/mathematical review are distinct obligations. A new manuscript version requires the actual reserved identity and complete public one-PDF verification; this mapping does not itself issue acceptance or perform publication. Negative findings remain negative.

The design in [design.md](design.md), all current requirement rows and their validation rows are explicit. Structural document checks verify these links and identifiers. They do not substitute for executing the functional gates or for independently reviewing a changed numerical or visual result.
