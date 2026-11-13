# Design: executable bilingual worked lessons

This current reconciliation explains the didactic layer and its proof obligations. It does not claim that the expanded lessons or this design were reviewed before their earlier versions existed. The product's mathematical methods live in public packages and named pipeline functions; a notebook explains and exercises those methods rather than defining an alternate implementation.

## Topic structure and scientific inputs

`notebooks/en/` and `notebooks/es/` mirror the same ordered topic and lesson paths. The progression moves from scalar pricing to hard-row control integrity, matched published formulations, the side-specific proposal and the directional group-peak proposal. The metadata declares language, topic, level, exact package pins, input paths and primary sources. Setup states the installation command and prints actual installed versions; it never installs into a running kernel.

The first four lessons use the ordinary pinned public `softqp` profile. The directional lesson invokes `pipeline.coupled_lessons.run_comparison` across its explicitly configured separate SDK environment. These profiles are not merged because their interfaces and registered scientific dependencies differ. The archived original and coupled results remain distinct from newly computed educational examples. Sensitivity sweeps change the declared educational problem and are not extra registered timing observations.

## Static semantic analysis

`scripts/check_notebooks.py` performs layout, metadata, mirror, source, cleanliness and content checks. It parses method-package sources without importing them to detect notebook definitions that shadow public method names. A static entrypoint registry in `product.json` distinguishes actual numerical method calls from file reads, version prints and arbitrary callbacks. `Reading`, `CallCounter` and their context tracking follow supported aliases, re-exports, method objects and declared factories while excluding methods of unrelated object attributes.

Method cells must genuinely run the product. A reference implementation alone cannot fill a level-three lesson's product-method minimum. Reader-only cells and comparisons against committed outputs have separate caps, preventing a saved-result viewer from passing as a worked method. Prose excludes setup, data, references, hidden comments, code and repeated sentences. Each plotted output needs immediate interpretation, and each answer must match a computed output number at the precision printed, not merely a setup version or a year.

The current content obligation exceeds the older template floors: at least 1000 explanatory words and two figures at level one; at least 1500 words and three figures at higher levels; governing display equations, valid sources and parameter/own-data sections. `notebooks/coverage.json` accounts for every method, contract, stage and method package. Counts are an admission screen; a separate reader judges derivation, relevance, result interpretation and the honesty of each coverage mapping.

## Fresh-kernel execution and external copies

`scripts/run_notebooks.py` discovers only correctly located notebooks and runs each from top to bottom in a fresh Python kernel. The ordinary runtime is resolved through the existing notebook environment alias. Method-package availability and exact pins are strict before execution. The runner clears old code outputs, coalesces stream fragments, retains only permitted metadata and assigns sequential execution counts through the execution itself.

`--check` requires an explicit external temporary root. It copies the required product inputs, including a declared `models/` folder when present, at the same relative depth, executes copies and compares cleaned bytes with committed notebooks. Temporary copies are removed afterward. Missing models or data are failures; no substitute checkpoint is created. Notebook execution is a local release gate rather than training in CI. Kernel transport notices in launcher logs do not authorize stored stderr, errors or machine paths in the final notebook.

## Limits and verification map

A deterministic educational example has no sampling confidence interval unless it actually includes repeated data or inferential resampling; the proposal lessons separately explain the uncertainty of their registered evidence. Raw JSON loading does not reproduce a complete journal analysis. Sources are tied to the SDD research basis, while numerical ownership and dependency licenses remain visible.

NB-041/NB-042/NB-091 cover external execution copies. NB-043 through NB-047 cover package discovery, shadowing, exact pins and opt-in PyPI reads. NB-048 through NB-061 and NB-066 cover worked content, mirrored anatomy and computed answers. NB-069 through NB-090 refine static entrypoint, prose and reproduction semantics. Exact controls are in `tests/test_check_notebooks.py` and `tests/test_run_notebooks.py`, with per-row links in [validation](validation.md) and [tasks](tasks.md). Independent notebook review remains distinct from this authoring design and its static checks.
