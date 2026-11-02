# Scientific manuscript sources

Two computational technical reports document the implemented methods, product scope and complete negative results.
Both use the prescribed native LaTeX report class, editable equations, ORCID, boxed front matter, running headers,
navy links and a bibliography. Their versioned PDFs are adjacent to the sources.

| Document | Editable source | Compiled PDF | Persistent concept |
|---|---|---|---|
| Product report, including the separable and coupled research scope | [main.tex](soft-constraint-study/main.tex) | [main.pdf](soft-constraint-study/main.pdf) | [Zenodo](https://doi.org/10.5281/zenodo.23851659) |
| Directional group-peak derivation and computational study | [main.tex](coupled-peak-study/main.tex) | [main.pdf](coupled-peak-study/main.pdf) | [Zenodo](https://doi.org/10.5281/zenodo.23875071) |

## Build and evidence

Install a LaTeX distribution providing pdflatex and configure an external CAOS_TEMP_ROOT. Run
`python manuscripts/soft-constraint-study/build.py` or `python manuscripts/coupled-peak-study/build.py`.
An explicit fresh `--output` directory may replace the scratch-root selection. The shared compiler performs
three passes and refuses warnings, missing glyphs, undefined references and overfull or underfull boxes.
Python exports checked numerical macros and invokes LaTeX; all scientific prose, mathematics and proofs live in main.tex.

The [coupled report instructions](coupled-peak-study/README.md) describe the immutable result/figure bindings.
The separate [evidence dataset](https://doi.org/10.5281/zenodo.23875194) retains every canonical input and raw observation.
Neither registered improvement criterion passed. Formatting changes and a development patch do not change that outcome.

## Publication state

The corrected reports are published as [product report 0.01.001](https://doi.org/10.5281/zenodo.23885690)
and [coupled report 0.02.001](https://doi.org/10.5281/zenodo.23885695). Both passed all 39 governed publication checks,
including fresh anonymous complete PDF download verification. Independent review additionally checked all 36 pages,
metadata, complete one-PDF inventories, latest/concept identity and all 22 public source/figure inputs.
The linked dataset preserves its original files and now reciprocally links both corrected reports.

Historical versions 23851660 and 23875072 remain immutable. Publication of these negative-result reports does not
establish algorithmic novelty, timing superiority or qualified product-release acceptance.
