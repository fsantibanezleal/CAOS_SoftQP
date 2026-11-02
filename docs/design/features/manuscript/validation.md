# Validation: scientific manuscript source and typesetting

| requirement | adversarial check | gate |
|---|---|---|
| MS-001 | Reject an absent LaTeX source, a false template identity, report-class paper or chapter command, incorrect document-type pairing or a custom Python manuscript generator. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_native_article_source` |
| MS-002 | Reject missing standard macros, missing concept identity or an incorrectly ordered title, header and abstract. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_standard_front_matter` |
| MS-003 | Reject missing ORCID, affiliation, running identity or navy hyperlink configuration. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_author_and_running_identity` |
| MS-004 | Reject manuscript equation images or omitted native mathematics and proofs. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_refuses_raster_equations` |
| MS-005 | Independently mutate each original/coupled source, population, signed estimate, interval and failure count; reject positive replacement, rehashed tampering or missing members. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_results_match_accepted_evidence` |
| MS-006 | Reject a build path that does not invoke the required compiler or check unresolved and clipped output. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_build_uses_latex` |
| MS-007 | Run the complete current report content and coverage check; reject missing methods/contracts, short explanations, missing algorithms, data figures or unsupported title labels. | `tests/test_manuscript_sources.py::test_adversarial_manuscripts_meet_current_content_bar` |
| MS-008 | Run the complete current paper check with separate original/coupled proposed-method coverage; inspect actual theory, original populations, uncertainty and component-comparison limits independently. | `tests/test_manuscript_sources.py::test_adversarial_manuscripts_meet_current_content_bar` |
| MS-009 | Mutate nested source/bibliography/figure during compilation and plant traversal/missing inputs; all are refused. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_source_change_during_build_is_refused` |
| MS-010 | Reject absent, false or transplanted independent source/content/math/page acceptance before any DOI/publication; final reserved DOI/PDF/metadata bindings have a separate final acceptance. | `tests/test_manuscript_sources.py::test_adversarial_publication_requires_independent_acceptance` |
