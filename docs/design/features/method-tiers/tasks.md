# Dependency graph and convergence: method tiers

The SDD defines the executable ladder before teaching metadata and manuscript coverage can be reconciled. Public naming is checked after those artifacts are authored. These are current implementation dependencies, not evidence that a metadata declaration proves a numerical contribution.

## Dependency sequence

| Unit | Requires | Requirements | Implementation responsibility | Production and test files |
|---|---|---|---|---|
| T1 | None | [MT-001](requirements.md), [MT-002](requirements.md), [MT-003](requirements.md) | Represent the full ladder, exact criteria and proposal correspondence | `docs/design/SDD.md`; `scripts/check_sdd.py`; `tests/test_method_tiers.py` |
| T2 | T1 | [MT-005](requirements.md) | Map published methods to actual level-three lessons in both languages | `scripts/check_notebooks.py`; `tests/test_method_tiers_notebooks.py` |
| T3 | T1 | [MT-006](requirements.md), [MT-007](requirements.md), [MT-008](requirements.md), [MT-009](requirements.md) | Declare and verify separately scoped publications and concept identities | `product.json`; `scripts/check_manuscripts.py`; `tests/test_check_manuscripts.py` |
| T4 | T2, T3 | [MT-010](requirements.md), [MT-011](requirements.md) | Keep internal classification out of reader-facing scientific content | `scripts/check_internal_names.py`; `tests/test_check_internal_names.py` |

## Exact requirement gates

Each requirement retains its own positive/behavioral gate and its distinct hostile check in [validation](validation.md). This table is an interface-to-proof map; it makes no claim that an unobserved command passed.

| Requirement | Dependency unit | Required gate from the current specification | Current convergence boundary |
|---|---|---|---|
| [MT-001](requirements.md) | T1 | `tests/test_method_tiers.py::test_adversarial_a_ladder_without_the_tier_column_fails_saying_how_to_add_it` (and `test_a_ladder_that_is_prose_fails_like_a_missing_column`, `test_adversarial_a_tier_that_is_not_one_of_the_three_fails`, `test_a_ladder_row_with_an_empty_method_or_a_repeated_id_fails`, `test_a_ladder_inside_a_code_fence_does_not_count`) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MT-002](requirements.md) | T1 | `tests/test_method_tiers.py::test_adversarial_a_product_without_a_method_in_a_tier_fails_naming_the_tier_and_the_rule` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MT-003](requirements.md) | T1 | `tests/test_method_tiers.py::test_adversarial_a_product_that_says_none_claimed_fails` (and `test_a_product_without_the_beyond_section_fails`, `test_a_product_with_no_claim_in_the_beyond_section_fails`, `test_none_claimed_next_to_a_claim_fails`, `test_adversarial_a_claim_with_only_a_validation_protocol_still_needs_a_beyond_method_row`, `test_adversarial_a_beyond_row_must_be_a_claim_of_the_section_and_a_claim_needs_its_row`) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MT-005](requirements.md) | T2 | `tests/test_method_tiers_notebooks.py::test_adversarial_a_sota_method_no_level_3_notebook_names_is_found_in_each_language` (and `test_adversarial_a_level_3_notebook_that_names_no_method_is_found`, `test_a_method_that_is_not_a_sota_row_of_the_ladder_is_found`, `test_methods_on_a_notebook_that_is_not_level_3_is_found`, `test_methods_must_be_a_list_of_strings`, `test_adversarial_the_two_languages_name_the_same_methods`) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MT-006](requirements.md) | T3 | `tests/test_check_manuscripts.py::test_adversarial_a_product_without_the_field_fails_with_the_rule` (and `test_adversarial_a_product_with_an_empty_list_fails_with_the_rule`, `test_a_product_with_only_a_manuscript_fails_it_needs_a_report`, `test_adversarial_the_template_may_declare_no_manuscript`) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MT-007](requirements.md) | T3 | `tests/test_check_manuscripts.py::test_adversarial_a_malformed_entry_fails_naming_the_field` (and `test_adversarial_a_manuscript_that_covers_a_claim_the_sdd_does_not_list_fails`, `test_a_repeated_concept_doi_fails`, `test_an_unknown_field_of_an_entry_fails`) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MT-008](requirements.md) | T3 | `tests/test_check_manuscripts.py::test_adversarial_a_report_version_behind_the_release_passes_unless_the_release_changes_a_result` (and `test_a_report_version_ahead_of_the_release_fails`) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MT-009](requirements.md) | T3 | `tests/test_check_manuscripts.py::test_adversarial_the_default_run_never_touches_the_network` (and `test_adversarial_the_online_check_finds_a_version_behind_the_declared_one`, `test_the_online_check_finds_a_missing_record_and_a_different_concept_doi`) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MT-010](requirements.md) | T4 | `tests/test_check_internal_names.py::test_adversarial_a_notebook_heading_or_title_with_a_tier_name_fails` (and `test_adversarial_a_tier_name_in_notebook_prose_code_or_output_fails`, `test_adversarial_a_manuscript_with_a_tier_name_fails`, `test_adversarial_an_index_the_readme_or_a_manuscript_title_with_a_tier_name_fails`, `test_adversarial_an_app_string_with_a_tier_name_fails`) | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [MT-011](requirements.md) | T4 | `tests/test_check_internal_names.py::test_adversarial_a_cited_title_in_references_a_key_string_a_fence_and_a_marked_line_pass` (and `test_a_product_that_names_its_methods_passes`, `test_the_template_passes`) | Implementation mapped; current gate execution is a separate acceptance obligation. |

## Current convergence

The ladder, mirrored published-method metadata and separate report/preprint declarations are present. An entry remains a proposal until its real evaluation supports more; neither current timing criterion does. Default CI reads no publication service; the explicit online check and actual deposit are separate evidence. The current every-proposal manuscript obligation supersedes an older introductory phrase that limited manuscripts to interesting findings.

The design in [design.md](design.md), all current requirement rows and their validation rows are explicit. Structural document checks verify these links and identifiers. They do not substitute for executing the functional gates or for independently reviewing a changed numerical or visual result.
