# Scientific document sources

The product technical report and research preprint are separate documents. Both derive their presentation from
the canonical CAOS Research foundational LaTeX article: native equations, section structure, ORCID, boxed
document identity, running headers and navy links. The research paper contains no chapters.

| Document | Editable revision source | Published PDF | Persistent concept |
|---|---|---|---|
| Seven Methods for Soft-Constraint Quadratic Programming: Contracts and Two Negative Timing Studies | [main.tex](soft-constraint-study/main.tex) | [main.pdf](soft-constraint-study/main.pdf) | [Technical report](https://doi.org/10.5281/zenodo.23851659) |
| Original-Row Proximal Splitting for Side-Specific and Directional Peak Penalties: Two Negative Timing Studies | [main.tex](coupled-peak-study/main.tex) | [main.pdf](coupled-peak-study/main.pdf) | [Research preprint](https://doi.org/10.5281/zenodo.23875071) |

The report covers all seven executable method rows and all eighteen contracts, including nested schema fields
and conditional rules. The paper develops each proposed update separately, with its own derivation, experiment
and limitations. Coverage maps bind those requirements to distinct source sections. Primary bibliography,
algorithms, physical units, complete populations, uncertainty and unsuccessful outcomes are included.

The editable sources on this branch are working revisions. The two published PDFs in the table correspond
to the source tree at commit [bbdd790](https://github.com/fsantibanezleal/CAOS_SoftQP/tree/bbdd7909b2ee523881383764eb969eaab079d4de/manuscripts).
Running the documented build creates draft PDFs in an external directory.

## Build and evidence

Install a LaTeX distribution providing pdflatex, BibTeX, Latin Modern, AMS mathematics, algorithm/algpseudocode,
graphicx, booktabs, longtable, hyperref, xurl, orcidlink and fancyhdr. Install the isolated figure dependencies with
`python -m pip install -r manuscripts/shared/requirements.txt`.

`python manuscripts/shared/generate_assets.py` verifies all thirty-nine immutable evidence inputs and derives
vector PDF figures and literal tables. It performs no optimization, timing measurement or bootstrap recomputation.
All scientific prose and mathematics are editable native `.tex` sources; Python does not lay out the documents.

Set an external `CAOS_TEMP_ROOT`, then run `python manuscripts/soft-constraint-study/build.py` or
`python manuscripts/coupled-peak-study/build.py`. Alternatively supply a fresh external `--output` directory.
The compiler checks the complete content bar, distinct coverage regions and both numerical authorities, then
runs BibTeX and three to six LaTeX passes until cross-references stabilize. Warnings, unresolved references,
missing glyphs and overfull or underfull boxes are refused. The build receipt binds recursive sources,
bibliography, vector figures, coverage, evidence manifests, compiler and policy dependencies before and after build.

`python scripts/manuscript_content_bar.py . --report` displays the full measured content checks.
`tests/test_manuscript_sources.py` plants altered numerical results, erased evidence inventories, reused coverage
sections, changed nested inputs, raster figures and forged publication acceptance. Successful compilation or
word counts do not replace independent content, mathematical and every-page review.

The separate [evidence dataset](https://doi.org/10.5281/zenodo.23875194) retains the grouped study's complete
canonical inputs and raw observations. The original 456-instance and grouped 210-instance studies remain distinct.
Both registered timing criteria failed. Historical publication and software archive versions remain immutable.

## Publication

New manuscript versions require independent acceptance before DOI reservation, followed by final reserved-DOI,
PDF and metadata acceptance before publication. Each manuscript record carries exactly one PDF. Editable sources
and supporting artifacts remain in Git and the separate dataset. The technical report is a report; the research
manuscript is a preprint. Publication does not establish scientific superiority or qualified product acceptance.

The current independently verified versions are [technical report 0.01.002](https://doi.org/10.5281/zenodo.23899079)
and [research preprint 0.02.002](https://doi.org/10.5281/zenodo.23899142). Each passed all 39 governed publication checks;
anonymous complete public PDFs, exact metadata and public editable sources were independently verified.

[Independent reciprocal dataset verification](independent-public-dataset-relations-review.md) confirms both new citations,
all historical relations and the unchanged original dataset version and file objects.
