# Original-row proximal updates: research manuscript

The editable manuscript is [main.tex](main.tex), using native LaTeX equations,
proofs and preprint front matter from the canonical section-based article template.
It derives side-specific interval and directional disjoint group-peak updates in
separate sections and reports their distinct registered timing studies.
[build.py](build.py) verifies numerical evidence before invoking the shared
native LaTeX driver. The product technical report remains a separate document.

## Build

Use pdflatex and BibTeX with the packages and isolated vector-figure dependencies
listed in the [document build instructions](../README.md). Set an external scratch root:

```powershell
python manuscripts/coupled-peak-study/build.py
```

`CAOS_TEMP_ROOT` selects the external build location; `--output` may instead name
an explicit fresh directory. The compiler runs three to six passes and rejects unresolved
references, warnings, missing glyphs and overfull or underfull boxes. The build
receipt binds the actual LaTeX inputs, figures and driver before and after the
compilation. Successful compilation does not replace inspection of every page or
independent mathematical and publication review.

The numeric `results.tex` is a checked export of the complete reviewed summary.
`--refresh-results` exports those numeric macros only. Immutable acceptance
anchors require the actual independent evidence/figure receipts and exact five-file
summary inventory; edited checksums cannot accept a fabricated result.

## Scientific scope

The directional study retains 210 authored synthetic inputs and 7770 observations.
The heldout score is -212.449875%, with a 95% seed-cluster interval
[-225.336618%,-192.873759%] and nine failed pairs. The registered 10% criterion is
not established. The separate original study contains 456 instances; its primary
has 24 distinct problems and 168 paired repetitions, with estimate 0.499839% and
95% seed-cluster interval [-3.291967%,3.944835%]. Its ten-percent criterion also fails.
Neither study replaces the other or supplies an unperformed causal ablation.

See [package and data requirements](reproduction.md). No operational or private
external dataset is needed. Full journals, CSV and canonical inputs are in the
separate [evidence dataset](https://doi.org/10.5281/zenodo.23875194).

The [research preprint concept](https://doi.org/10.5281/zenodo.23875071) is separate
from the product technical report. Replacement publication requires independent
content, mathematics and every-page acceptance, a final reserved-DOI build and
matching metadata/file review. Historical versions remain immutable. Publication
does not establish timing superiority, algorithmic priority or qualified product acceptance.
