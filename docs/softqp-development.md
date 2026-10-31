# Scientific development run

The native methods are provided by the separately versioned [SoftQP engine](https://github.com/fsantibanezleal/CAOS_SoftQP_Engine). Install the exact source pin and dependencies in `requirements-softqp.txt`, using Python 3.12 and a C/C++ compiler with CMake.

```bash
python -m pip install -r requirements-softqp.txt
python -m pytest tests/test_softqp_matrix.py -q
python data-pipeline/run_softqp.py --output /path/to/development-results
```

The explicit output directory prevents a test or exploratory run from replacing committed results. The development bake covers fifteen declared case IDs with explicit available, failed or incompatible method cells. It writes an index with SHA-256 digests, solver settings and environment versions. Timings are measurements of individual development runs and are not a repeated benchmark or a speedup claim.

The paper building model is adapted from OSQPSlack under MIT; its source is in `data-pipeline/pipeline/energy_reference.py`, with attribution and the original license in `data/licenses/OSQPSlack-MIT.txt`. C13 retains the original mixed penalty model. C14 and C15 deliberately replace those penalties with authored separable side-specific costs and must be interpreted as changed scenarios.

Current coverage limits: DAQP and FlexQP are not executed by this development runner. C12 is an initial parameter-stream state and does not yet establish warm-start behavior. The app and its inherited example routes are still being replaced. The development bake is not a release acceptance matrix. See the product SDD for complete requirements and release gates.
