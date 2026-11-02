# Scientific pipeline stages

`data-pipeline/run.py all --output OUTPUT` is the explicit scientific bake. Output is mandatory, even when the intended destination is the canonical tree. Tests use their own temporary roots and a session guard rejects mutations of committed data or model files. Do not edit either guarded tree while pytest is running.

1. **Validate.** Check sparse dimensions, finite coefficients, symmetric positive-semidefinite P, interval directions and nonnegative side prices. The standalone CSC decoder also checks offsets, lengths and sorted unique row indices.
2. **Assemble.** Construct authored cases or the preserved published building model. Retain original physical units and hard policy. Select a compatible solver formulation without changing the objective to fit an adapter.
3. **Solve.** Execute native generalized/asymmetric projection, independent lifting or an explicitly supported reference adapter. An unsupported family becomes an incompatible cell; a numerical failure remains failed with its reason.
4. **Evaluate.** Recover original x/y, recompute base and penalty objective, lower/upper violations and raw hard error. Compare successful cells to the declared oracle using the external tolerance rather than treating every backend success integer as equivalent.
5. **Export.** Validate JSON Schema, write finite UTF-8 records, build the SHA-256 inventory and wrap the scientific records in deployment manifests. Readiness is recomputed from the actual catalog and inventory.

The separate experiment runner adds registered seed splits, randomized paired method order, warm-ups, seven measured repetitions, time/RSS limits, retained JSONL/CSV and cluster-aware summaries. A common high-accuracy stock oracle drives the 32-frame C12 trajectory; all methods receive identical state inputs. The stream records initial setup independently from update/solve work.

There is no fitted model or training stage. Deterministic optimization and a learned parameter policy are distinct capabilities; Deep FlexQP training assets are not supplied. See [evaluation](06_model-evaluation.md) and [the registered protocol](../design/experiments-v1.json).
