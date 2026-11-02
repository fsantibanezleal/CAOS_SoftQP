# Validation: scientific manuscript source and typesetting

| requirement | adversarial check | gate |
|---|---|---|
| MS-001 | Reject an absent LaTeX source, an incorrect document class or the custom Python manuscript generator. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_native_report_source` |
| MS-002 | Reject missing standard macros, missing concept identity or an incorrectly ordered title, header and abstract. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_standard_front_matter` |
| MS-003 | Reject missing ORCID, affiliation, running identity or navy hyperlink configuration. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_requires_author_and_running_identity` |
| MS-004 | Reject manuscript equation images or omitted native mathematics and proofs. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_refuses_raster_equations` |
| MS-005 | Compare the manuscript result macros against the accepted summary, including all failed pairs and counts. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_results_match_accepted_evidence` |
| MS-006 | Reject a build path that does not invoke the required compiler or check unresolved and clipped output. | `tests/test_manuscript_sources.py::test_adversarial_manuscript_build_uses_latex` |
