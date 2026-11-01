# Scientific pipeline

The product runs convex soft-constrained quadratic programs with a separately versioned native engine. It declares no Python distribution inside this repository.

## Run

Install `requirements-softqp.txt` with Python 3.12, a C/C++ compiler and CMake. Then:

```bash
python data-pipeline/run.py all --output ./local-derived
python data-pipeline/run.py readiness
python data-pipeline/run_request.py C01-request.json --output local-result.json
```

The full bake requires an explicit output directory. Use `--output data/derived` only for an intentional canonical bake. Tests always write to temporary directories and the test sandbox checks that committed scientific files remain unchanged.

## Stages and ownership

1. **Validate** sparse dimensions, coefficient types, finite numbers, interval bounds, convexity and side costs.
2. **Assemble** the authored catalog, condensed controller or licensed building model and original-row metadata.
3. **Solve** every compatible formulation: compact explicit lifting, published generalized projection, separable asymmetric projection and DAQP.
4. **Evaluate** the original objective, physical side violations, hard-row error, stationarity where available and agreement with independent lifting. Available cells must also pass the original-space acceptance check.
5. **Export** strict result JSON, a digest inventory, deployment manifests and deterministic readiness.

`pipeline/softqp_cases.py` defines all fifteen cases. `softqp_rows.py` assigns bilingual labels, units and hard/soft policy. `softqp_run.py` owns execution and checksummed export; `io/contract.py` ingests sparse problem records; `softqp_requests.py` executes bounded cost edits tied to an existing case digest. `core/manifest.py` wraps the scientific records for the static deployment. There is no unrelated training or surrogate-model stage.

## Mathematical boundary

The Hessian is a full symmetric positive semidefinite matrix. JSON stores CSC matrices as shape, values, row indices and column offsets. Row indices must be sorted and unique inside each column. A null lower endpoint represents negative infinity; a null upper endpoint represents positive infinity. A boolean cannot substitute for a number.

Separable cases retain lower and upper linear and quadratic coefficients per row. Hard rows remain hard. Coupled group and Huber cases use the exact published reference path and cannot be silently converted to independent side penalties. DAQP refuses incompatible curvature or costs and inserts no regularizer.

## Evidence limits

Seeds reproduce authored inputs. Runtime and solver iteration histories can vary, so two native executions need not have identical bytes. A digest identifies one exported execution. The canonical matrix is development evidence, with a visible reason for every incompatible or failed method cell. C12 streaming, repeated held-out timing, current-method reproduction and research/release acceptance remain separate requirements. See [the local workflow guide](../docs/softqp-development.md).
