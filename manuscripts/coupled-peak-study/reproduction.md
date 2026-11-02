# Coupled study: package and data requirements

The public package is [`softqp==0.2.0`](https://pypi.org/project/softqp/0.2.0/).
Use a fresh CPython 3.12 environment for this registered study. Install its complete
pinned profile from `experiments/coupled-v1/requirements.txt` in
[app source 246bf87](https://github.com/fsantibanezleal/CAOS_SoftQP/tree/246bf87e690f4d010494c556e2021d311d587422).
The profile includes NumPy, SciPy, OSQP, DAQP, ElastiQP, jsonschema, pytest and
packaging at the exact registered versions. Installing the SDK alone is sufficient
for its API, but does not install every comparison backend used by the study.

```powershell
py -3.12 -m venv .venv-coupled
.venv-coupled\Scripts\python.exe -m pip install -r experiments/coupled-v1/requirements.txt
.venv-coupled\Scripts\python.exe data-pipeline/run_coupled_study.py --check-freeze
```

No external operational dataset, customer data or private building records are
required. The frozen source generates authored synthetic sparse quadratic problems
and two-zone thermal forecasts. The registered inventory is 48 development,
144 heldout and 18 robustness instances, each with 32 forecasts. Hard bounds,
physical units, objective coefficients and directional group penalties are retained
in the canonical batch documents. These data do not constitute measurements from
an operating building or a closed-loop controller deployment.

Each completed split retains the full raw oracle/method journal (`trials.jsonl`),
exact exported CSV, canonical inputs, protocol, provenance, campaign and validation
documents. Warmups, declared incompatibilities, backend limits, timeouts and failed
comparisons remain in the archive. The registered failed-pair score is retained in
the full 144-instance heldout population.

To replay a completed extracted split, use the registered source and environment:

```powershell
.venv-coupled\Scripts\python.exe data-pipeline/run_coupled_study.py --validate-output --output <extracted-split-directory>
```

A fresh execution requires a new output directory and the unchanged registration:

```powershell
.venv-coupled\Scripts\python.exe -u data-pipeline/run_coupled_study.py --split development --output output/new-development
.venv-coupled\Scripts\python.exe -u data-pipeline/run_coupled_study.py --split heldout --output output/new-heldout
.venv-coupled\Scripts\python.exe -u data-pipeline/run_coupled_study.py --split robustness --output output/new-robustness
```

Keep the historical 0.1.0 notebook/product environments and original 456-instance
study separate. Their package pins, outputs and published report are immutable.
The new study's accepted evidence means that its recorded execution is faithfully
reproduced; it does not mean its speed criterion passed. The coupled heldout result
is negative and does not qualify an app release or superiority claim. Runtime
measurements come from one recorded nonreserved host and are not expected to be
bit-for-bit reproducible across hardware or concurrent workloads.

Final complete-evidence, figure, archive and report review receipts identify the
accepted bytes. The technical-report publication contains one PDF; its supporting
evidence is published separately with reciprocal supplement relations.
