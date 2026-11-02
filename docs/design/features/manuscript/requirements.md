# Requirements: scientific manuscript source and typesetting

The complete product technical report and the proposed-method research paper are
separate documents. Both derive their presentation from the actual CAOS Research
foundational article preamble. The report is labelled Technical report; the paper
is labelled Preprint and uses sections, never chapters. Their results remain
negative; authoring and rendering do not change either registered computation.

| ID | Requirement | Gate |
|---|---|---|
| MS-001 | THE two documents SHALL exist as separate editable native LaTeX article sources derived from the identified base preamble, with section-numbered theorems and no chapter commands; the complete report and research paper SHALL have distinct appropriate document-type labels. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_native_article_source` |
| MS-002 | THE front matter SHALL use the standard document identity macros and place the prescribed boxed header after the title and before the abstract, with both version and concept identifiers. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_standard_front_matter` |
| MS-003 | THE manuscript SHALL carry the sole author with an ORCID icon, the programme affiliation, navy links and running document-type/version headers. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_author_and_running_identity` |
| MS-004 | THE equations and derivations SHALL be native LaTeX; included graphics SHALL be vector PDF figures generated from identified product evidence and bound to an exact generated inventory, at least ten in the report and six in the paper, never equation screenshots. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_refuses_raster_equations` |
| MS-005 | THE two documents SHALL obtain both studies' estimates, confidence limits, populations, failures and state counts from their separate immutable authorities: original 456-instance computation/168 paired endpoint and coupled 210-instance computation/144 paired endpoint; changing one authority, denominator or signed statistic SHALL be refused independently. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_results_match_accepted_evidence` |
| MS-006 | THE build entrypoint SHALL compile the LaTeX source with pdflatex and SHALL refuse unresolved references or clipped typesetting rather than rendering document text or equations through a PDF graphics library. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_build_uses_latex` |
| MS-007 | THE report SHALL meet every required section and measured floor of the current manuscript content bar, including 12000 prose words, 25 displayed equations, ten figures, eight tables, 30 cited works, and every seven-method and eighteen-contract explanation, without generic padding. | `tests/test_manuscript_sources.py::test_adversarial_manuscripts_meet_current_content_bar` |
| MS-008 | THE research paper SHALL separately derive both related proposals and attribute each experiment to its original population; each method SHALL have 1500 prose words and six equations; the complete paper SHALL meet the 7000-word and remaining research-paper floors, including an accurately limited ablation analysis. | `tests/test_manuscript_sources.py::test_adversarial_manuscripts_meet_current_content_bar` |
| MS-009 | THE compiler SHALL bind every recursively included local source, bibliography and figure before and after compilation and SHALL refuse traversal, missing inputs or source mutation; the measured-content check SHALL run before compilation and publication. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_source_change_during_build_is_refused` |
| MS-010 | WHEN publication is prepared, THE publisher SHALL require independent content, mathematics, per-page visual and exact-source acceptance before reserving or publishing new same-concept versions; the paper metadata SHALL identify a preprint and the report metadata a report. | `tests/test_manuscript_sources.py::test_adversarial_publication_requires_independent_acceptance` |

Publication additionally requires scientific-voice validation, full compilation,
inspection of every rendered page, independent mathematical and source review,
source/metadata/PDF hash binding, the actual reserved identifier on page one and
fresh verification of the complete public one-PDF inventory. These are release
acceptance obligations; source checks alone never establish them.
