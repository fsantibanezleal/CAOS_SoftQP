# Requirements: scientific manuscript source and typesetting

Both the separable and coupled studies are computational technical reports. Their
scientific results remain negative. Formatting corrections do not change either
registered computation. The source requirements apply to both manuscripts; numerical
macros for the coupled study bind to its independently reviewed summary.

| ID | Requirement | Gate |
|---|---|---|
| MS-001 | THE manuscript SHALL exist as an editable native LaTeX source using the report class, with its scientific text in that source rather than a Python PDF generator. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_native_report_source` |
| MS-002 | THE front matter SHALL use the standard document identity macros and place the prescribed boxed header after the title and before the abstract, with both version and concept identifiers. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_standard_front_matter` |
| MS-003 | THE manuscript SHALL carry the sole author with an ORCID icon, the programme affiliation, navy links and running document-type/version headers. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_author_and_running_identity` |
| MS-004 | THE equations and derivations SHALL be native LaTeX; graphics inclusion SHALL be confined to each manuscript's declared evidence-derived figure inventory, five figures in the separable study and two in the coupled study, never equation screenshots. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_refuses_raster_equations` |
| MS-005 | THE manuscript SHALL obtain its primary estimate, confidence limits, failed-pair count and measured-state counts from the accepted complete-study summary without changing the population or criterion. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_results_match_accepted_evidence` |
| MS-006 | THE build entrypoint SHALL compile the LaTeX source with pdflatex and SHALL refuse unresolved references or clipped typesetting rather than rendering document text or equations through a PDF graphics library. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_build_uses_latex` |

Publication additionally requires scientific-voice validation, full compilation,
inspection of every rendered page, independent mathematical and source review,
source/metadata/PDF hash binding, the actual reserved identifier on page one and
fresh verification of the complete public one-PDF inventory. These are release
acceptance obligations; source checks alone never establish them.
