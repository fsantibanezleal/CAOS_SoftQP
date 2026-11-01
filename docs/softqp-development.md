# Scientific development and local execution

SoftQP Studio executes optimization with the separately versioned [SoftQP engine](https://github.com/fsantibanezleal/CAOS_SoftQP_Engine). Python 3.12, a C/C++ compiler and CMake are required to install the exact source pin in `requirements-softqp.txt`.

```bash
python -m pip install -r requirements-softqp.txt
python -m pytest tests/test_softqp_matrix.py tests/test_softqp_contracts.py tests/test_softqp_requests.py -q
python data-pipeline/run_softqp.py --output ./local-results
```

An explicit output directory prevents exploratory runs from replacing committed records. The fifteen-case development matrix executes explicit lifting, published generalized projection, the separable asymmetric extension and DAQP on compatible formulations. All cells retain available, failed or incompatible states. DAQP requires positive definite curvature and positive quadratic soft costs; it inserts no regularizer. Pure L1 edits additionally run a paper-equation FlexQP reconstruction and published ElastiQP 0.2.0; the learned Deep FlexQP policy is not implemented.

The building model is adapted from OSQPSlack under MIT. Attribution is in `data-pipeline/pipeline/energy_reference.py` and `data/licenses/OSQPSlack-MIT.txt`. C13 preserves the original mixed penalties. C14 and C15 replace them with declared authored separable side costs.

## Edit costs, solve locally, inspect

1. Open the App, select a separable case, and expand **Edit costs and solve locally**.
2. Set lower, upper and quadratic multipliers between 0.01 and 100 (the quadratic factor also allows zero). Lower/upper factors multiply the corresponding linear and quadratic soft costs; the quadratic factor further multiplies both quadratic sides. Hard rows are unchanged. A zero quadratic factor explicitly chooses a pure L1 variant and executes the compatible fixed-parameter FlexQP reconstruction and published ElastiQP reference, with reasons for incompatible cells.
3. Download the solve request. In a checkout matching the displayed inventory, run:

   ```bash
   python data-pipeline/run_request.py C01-request.json --output local-result.json
   ```

4. Import the local result in the App. It checks the request, unchanged matrices and row policy, schema, original objective, side violations and comparison gaps before displaying it. Restore the original record with its dedicated control.

The CLI verifies the base artifact digest and its serialized matrices against the current source catalog before applying edits. A stale request must be regenerated against matching data; it is never silently rebased. Coupled penalties in C05 and C13 are not converted to separable costs. The browser sends no request or result to a server.

## Evidence boundaries

The browser replays committed or locally imported native records. A browser solver has not been enabled. The fixture source is isolated: build with `VITE_SOFTQP_SOURCE=fixture` for its C01-only inventory; the interface labels that provider explicitly. The actual loader and checksum checks are tested for both sources.

Timings are individual development observations, not a repeated benchmark or speedup claim. C12 is currently a stream's initial state; its complete stream evidence is being implemented. The scientific pipeline and deployment inventories replace the inherited domain core. Remaining old documentation and notebooks are still being migrated. Source checks, full UI gates, notebooks, report, deployment proof and research acceptance remain distinct unfinished release requirements.
