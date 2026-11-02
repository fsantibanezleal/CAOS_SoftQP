# Run the scientific bake

Install the exact scientific requirements in an isolated Python 3.12 environment. A source install of the native engine requires CMake and a C/C++ compiler; a supported published wheel avoids that local build. The app itself is invoked by path and is not installed as a package.

```bash
python -m pip install -r data-pipeline/requirements.txt
python data-pipeline/run.py all --output data/derived
python scripts/check_documents.py
python scripts/check_artifacts.py
python scripts/check_readiness.py
```

Choose a temporary output root for development experiments or tests. The canonical destination above is intentional: it replaces the published scientific bake. Do not run it while pytest's data guard is active. `python data-pipeline/run.py readiness` only recomputes readiness and does not run a solver.

The fifteen case records land under `softqp/`, with a scientific index and deployment wrappers under `manifests/`. Original x/y, cost components, row metadata, solver status and compatibility are retained. Individual elapsed fields have their backend-specific scope; the statistical runner owns cold end-to-end measurement.

```bash
python data-pipeline/run_experiments.py stream --output OUTPUT
python data-pipeline/run_experiments.py campaign --output FRESH_OUTPUT
```

The campaign refuses existing trial evidence and enforces its registered source and thread settings. Preserve its complete output, including failures, rather than rerunning until a favorable result appears. Verify and publish the final evidence with the experiment export function documented in [the development workflow](../softqp-development.md). The [protocol](../design/experiments-v1.json) records the source, seed splits and primary outcome.
