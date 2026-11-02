# Scientific data and provenance

All fifteen cases are synthetic mathematical models. No operational building measurements, personal records or client data are distributed.

- C01-C04 and C11 are authored scalar or mixed hard/soft policy examples.
- C05 is an authored coupled maximum-penalty example using the published reference implementation.
- C06-C08 are seeded sparse, semidefinite and ill-conditioned generated problems.
- C09, C10 and C12 use an authored condensed double-integrator controller with twenty steps and a 0.2-second sampling interval. C12 currently records only the initial stream state.
- C13 reproduces the OSQPSlack two-zone building, battery and grid model with its original mixed penalties. The copied model preserves its MIT license and attribution in `data-pipeline/pipeline/energy_reference.py`; the license is [licenses/OSQPSlack-MIT.txt](licenses/OSQPSlack-MIT.txt).
- C14 and C15 deliberately replace C13's mixed penalties with authored separable side costs. They are changed scenarios, not an unchanged reproduction of the paper's objective.

`derived/softqp/` contains the native result records and SHA256 inventory. Each record preserves original row units and policy, source, numerical settings, dimensions, costs, violations and method states. Sparse original inputs accompany separable cases. `derived/manifests/` declares exactly which files the static deployment copies, their sizes, digests and precompute-lane reason. `derived/readiness.json` is generated from the catalog and actual inventory.

The independent provider in `docs/contracts/fixtures/data/derived` contains C01 only. It exercises the same schema, digest, deployment and consumer boundaries; it is not additional experimental data. Raw or private inputs belong in ignored `raw/` and are not part of this authored catalog.

The records are development evidence. Individual timings do not establish speed superiority, and small hard-row residuals do not establish engineering safety. Reproducible experiment and release acceptance are tracked separately.
