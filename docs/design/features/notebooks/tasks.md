# Dependency graph and convergence: notebooks

Package/source admission and static method attribution precede lesson execution. Computed answers, figures and cross-language coverage are then checked against the actual saved outputs. This current graph describes the implementation and quality obligations, not a substitute for an independent reader.

## Dependency sequence

| Unit | Requires | Requirements | Implementation responsibility | Production and test files |
|---|---|---|---|---|
| N1 | None | [NB-043](requirements.md), [NB-044](requirements.md), [NB-045](requirements.md), [NB-046](requirements.md), [NB-047](requirements.md), [NB-079](requirements.md) | Admit exact public packages and forbid notebook method copies | `product.json`; `notebooks/requirements.txt`; `scripts/check_notebooks.py` |
| N2 | N1 | [NB-048](requirements.md), [NB-069](requirements.md), [NB-070](requirements.md), [NB-076](requirements.md), [NB-078](requirements.md), [NB-086](requirements.md), [NB-087](requirements.md), [NB-089](requirements.md), [NB-090](requirements.md) | Resolve real method calls, aliases, factories and object boundaries | `scripts/check_notebooks.py`; `tests/test_check_notebooks.py` |
| N3 | N2 | [NB-049](requirements.md), [NB-050](requirements.md), [NB-051](requirements.md), [NB-052](requirements.md), [NB-053](requirements.md), [NB-054](requirements.md), [NB-055](requirements.md), [NB-056](requirements.md), [NB-061](requirements.md), [NB-072](requirements.md), [NB-073](requirements.md), [NB-074](requirements.md), [NB-081](requirements.md), [NB-082](requirements.md), [NB-088](requirements.md) | Measure substantive prose, figures and permitted machinery | `scripts/check_notebooks.py`; `scripts/notebook_bar.json` |
| N4 | N2, N3 | [NB-057](requirements.md), [NB-058](requirements.md), [NB-059](requirements.md), [NB-060](requirements.md), [NB-066](requirements.md), [NB-071](requirements.md), [NB-075](requirements.md), [NB-083](requirements.md) | Require distinct questions, computed answers and mirrored lesson anatomy | `notebooks/en/README.md`; `notebooks/es/README.md`; `tests/test_check_notebooks.py` |
| N5 | N1, N4 | [NB-041](requirements.md), [NB-042](requirements.md), [NB-091](requirements.md) | Execute fresh kernels and unchanged-output copies under external temp | `scripts/run_notebooks.py`; `tests/test_run_notebooks.py` |

## Exact requirement gates

Each requirement retains its own positive/behavioral gate and its distinct hostile check in [validation](validation.md). This table is an interface-to-proof map; it makes no claim that an unobserved command passed.

| Requirement | Dependency unit | Required gate from the current specification | Current convergence boundary |
|---|---|---|---|
| [NB-041](requirements.md) | N5 | `tests/test_run_notebooks.py::test_adversarial_check_without_a_temp_root_stops_with_exit_2` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-042](requirements.md) | N5 | `tests/test_run_notebooks.py::test_adversarial_check_writes_only_under_the_temp_root_and_removes_it` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-043](requirements.md) | N1 | `tests/test_check_notebooks.py::test_adversarial_the_public_names_of_a_method_package_are_read_without_importing_it` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-044](requirements.md) | N1 | `tests/test_check_notebooks.py::test_adversarial_a_notebook_that_defines_a_method_package_name_is_found` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-045](requirements.md) | N1 | `tests/test_check_notebooks.py::test_adversarial_a_method_package_that_is_not_installed_is_info_in_the_static_check` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-046](requirements.md) | N1 | `tests/test_check_notebooks.py::test_adversarial_a_method_package_without_a_pin_is_found` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-047](requirements.md) | N1 | `tests/test_check_notebooks.py::test_adversarial_the_pypi_check_fails_on_anything_but_200` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-048](requirements.md) | N2 | `tests/test_check_notebooks.py::test_nb048_method_cells` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-049](requirements.md) | N3 | `tests/test_check_notebooks.py::test_nb049_figures` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-050](requirements.md) | N3 | `tests/test_check_notebooks.py::test_nb050_words_after_each_figure` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-051](requirements.md) | N3 | `tests/test_check_notebooks.py::test_nb051_explanatory_prose_words` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-052](requirements.md) | N3 | `tests/test_check_notebooks.py::test_nb052_setup_and_input_output_cells` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-053](requirements.md) | N3 | `tests/test_check_notebooks.py::test_nb053_reproduction_checks` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-054](requirements.md) | N3 | `tests/test_check_notebooks.py::test_nb054_sentences_shared_with_another_notebook` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-055](requirements.md) | N3 | `tests/test_check_notebooks.py::test_nb055_generic_filler_sentences` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-056](requirements.md) | N3 | `tests/test_check_notebooks.py::test_nb056_two_statements_on_one_line` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-057](requirements.md) | N4 | `tests/test_check_notebooks.py::test_nb057_the_first_cell_states_the_question_in_each_language` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-058](requirements.md) | N4 | `tests/test_check_notebooks.py::test_nb058_the_answer_quotes_a_number_that_an_output_shows` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-059](requirements.md) | N4 | `tests/test_check_notebooks.py::test_nb059_level_three_runs_the_state_of_the_art_and_draws_it` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-060](requirements.md) | N4 | `tests/test_check_notebooks.py::test_nb060_level_four_shows_a_figure_or_a_table_under_beyond` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-061](requirements.md) | N3 | `tests/test_check_notebooks.py::test_nb061_a_notebook_without_a_valid_level_is_measured_at_level_two` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-066](requirements.md) | N4 | `tests/test_check_notebooks.py::test_nb057_the_first_cell_states_the_question_in_each_language` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-069](requirements.md) | N2 | `tests/test_check_notebooks.py::test_b2_import_names_are_static_and_never_read_from_the_environment` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-070](requirements.md) | N2 | `tests/test_check_notebooks.py::test_b1_readers_loaders_versions_and_dunder_chains_are_no_method_cells` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-071](requirements.md) | N4 | `tests/test_check_notebooks.py::test_b4_the_answer_is_matched_at_the_precision_a_reader_writes_it` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-072](requirements.md) | N3 | `tests/test_check_notebooks.py::test_m1_hidden_repeated_and_tabular_text_is_no_prose` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-073](requirements.md) | N3 | `tests/test_check_notebooks.py::test_m2_cells_that_only_read_and_print_are_input_output_cells` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-074](requirements.md) | N3 | `tests/test_check_notebooks.py::test_m3_the_forms_of_reproduction_check_the_review_found_are_counted` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-075](requirements.md) | N4 | `tests/test_check_notebooks.py::test_m4_two_notebooks_of_a_tree_do_not_share_a_question` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-076](requirements.md) | N2 | `tests/test_check_notebooks.py::test_m5_at_level_three_the_reference_implementation_alone_does_not_fill_the_floor` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-078](requirements.md) | N2 | `tests/test_check_notebooks.py::test_m7_the_modules_of_the_templates_src_skeleton_are_method_modules` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-079](requirements.md) | N1 | `tests/test_check_notebooks.py::test_nb1_a_product_must_declare_its_method_entrypoints` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-081](requirements.md) | N3 | `tests/test_check_notebooks.py::test_nb3_short_sentences_and_paragraphs_repeated_are_counted_once` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-082](requirements.md) | N3 | `tests/test_check_notebooks.py::test_nb4_only_declared_artifacts_are_committed_results_whatever_the_call_form` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-083](requirements.md) | N4 | `tests/test_check_notebooks.py::test_n3_the_answer_is_matched_by_magnitude_and_a_bare_exponent_is_no_answer` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-086](requirements.md) | N2 | `tests/test_check_notebooks.py::test_r22_the_return_value_of_a_function_and_a_container_method_earn_no_method_cell` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-087](requirements.md) | N2 | `tests/test_check_notebooks.py::test_r2_a_re_export_is_resolved_statically_from_the_package_or_from_the_map` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-088](requirements.md) | N3 | `tests/test_check_notebooks.py::test_m31_a_heading_a_label_and_a_short_pointer_may_come_back` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-089](requirements.md) | N2 | `tests/test_check_notebooks.py::test_m32_a_declared_factory_builds_a_method_object` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-090](requirements.md) | N2 | `tests/test_check_notebooks.py::test_m33_a_method_of_an_attribute_of_the_object_is_not_a_method_of_the_object` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [NB-091](requirements.md) | N5 | `tests/test_run_notebooks.py::test_adversarial_check_copies_models_so_a_notebook_can_run_a_released_model` | Implementation mapped; current gate execution is a separate acceptance obligation. |

## Current convergence

The lesson trees, real numerical entrypoints and runner exist. Current higher content floors, governing equations, sensitivity/own-data sections and whole-tool coverage additionally apply; passing the inherited lower floors cannot accept a thin lesson. Fresh execution, exact stored outputs and independent substantive/figure review remain separate from static method counting.

The design in [design.md](design.md), all current requirement rows and their validation rows are explicit. Structural document checks verify these links and identifiers. They do not substitute for executing the functional gates or for independently reviewing a changed numerical or visual result.
