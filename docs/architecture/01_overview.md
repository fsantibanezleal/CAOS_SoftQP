# System and ownership

The product begins with a convex original-space problem: symmetric positive-semidefinite P, q, sparse A, interval bounds and one hard/soft policy per row. A soft row has independent lower/upper linear and quadratic coefficients. Its physical unit is metadata on the original row, so a lift never substitutes auxiliary-variable units for the engineering quantity.

The separate `softqp` distribution owns the C solver extension, ordinary lifts, reference adapters, prepared workspaces and original-space recovery. The app is scripts rather than an internal Python distribution. Its `data-pipeline/pipeline/softqp_cases.py` defines the fifteen teaching cases; `softqp_rows.py` supplies units; `softqp_run.py` evaluates and exports them. The source-faithful building model is kept distinct from the two authored separable variants.

The frontend is a static consumer. `frontend/src/lib/softqp.ts` validates JSON and verifies exact bytes against SHA-256 before rendering case records. The experimental reader follows the same boundary for campaign and stream files. Generated TypeScript comes from the contract schemas; handwritten copies of interfaces are avoided.

One selected case belongs to the workbench. Cross-case outcomes belong to Experiments and Benchmark. The C12 stream uses a common independently driven trajectory, so its chart compares solver observations on identical state inputs rather than claiming a comparison of independent controllers. A reader may edit supported cost factors, export a request, execute it locally and import the result. There is no hosted optimization endpoint.

Ownership matters for releases: a green app build cannot prove the native wheel is installable, and an engine release cannot establish that the app serves the correct artifact inventory. Each repository records its own source and promotion evidence. See the [contract catalog](../contracts/catalog.md) and [native source repository](https://github.com/fsantibanezleal/CAOS_SoftQP_Engine).
