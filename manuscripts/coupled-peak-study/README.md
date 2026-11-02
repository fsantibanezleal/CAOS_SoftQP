# Directional coupled peak study

This standalone computational-study report documents the coupled-penalty revision
and its negative prospectively registered result. It is separate from the product's
0.01.000 technical report, historical study, product version and release gate.
Its source experiment is app commit `246bf87e690f4d010494c556e2021d311d587422`.
No frozen experiment source or historical notebook environment is changed.

The complete study has 210 canonical synthetic instances and 7770 raw observations.
Independent review accepts the integrity of all three splits; it does not establish
the registered speed criterion. The full-population heldout score is -212.449875%,
95% seed-cluster interval [-225.336618%,-192.873759%], with nine failed pairs retained.

See [package and data requirements](reproduction.md). No operational dataset or
private records are required. Full raw journals, CSV, canonical inputs and protected
source snapshots belong in a separately reviewed evidence archive. The manuscript
publication contains one PDF only, with reciprocal supplement relations to data.

The three helpers enforce successive gates:

1. `render-study-summary.py` requires complete development/heldout/robustness
   artifacts and an independent `ACCEPT_EVIDENCE` receipt before plotting.
2. `package-study-evidence.py` additionally requires exact `ACCEPT_FIGURES`
   acceptance, verifies every member and publishes a new ZIP plus checksum.
3. `build-coupled-report.py` additionally requires independent `ACCEPT_ARCHIVE`
   acceptance before rendering equations and producing a new PDF. Optional
   `--doi` and `--evidence-doi` embed the actually reserved publication identities.

Use `--help` for each helper's path arguments. Summary/equation rendering was
verified with Matplotlib 3.11.2 and NumPy 2.5.4. PDF generation uses ReportLab 4.4.9
with its included Vera fonts. These are postprocessing dependencies, separate from
the frozen experiment profile. Every rendered page and figure requires independent
visual review; successful source/preflight checks alone do not accept a PDF.

The earlier published report remains [version 0.01.000](https://doi.org/10.5281/zenodo.23851660).
The current record's reserved/published identifiers are recorded in its publication
receipt once those external gates complete. No DOI is inferred from a local build.
