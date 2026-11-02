# Numerical backend scope

The implemented engine uses the CPU builtin sparse linear-system backend. No GPU solver or trained parameter policy is declared. The small reference adapters may convert a compatible problem to dense arrays, but dense conversion is bounded and does not make it a GPU method.

The native package checks penalty semantics and the supported backend before setup. A future accelerator must preserve lower/upper coefficients, hard rows, original dual recovery, scaling and recession behavior over the complete matrix. It also needs measured setup, transfer, solve, memory and end-to-end cost under a fair protocol. A successful device import or a faster isolated matrix multiplication is insufficient.

Use one numerical campaign worker and the registered BLAS/OMP/MKL thread limits for the current comparisons. Native binary rebuilds and imports must be sequential on Windows to avoid replacing a loaded extension. Do not install a new editable binary into the environment used by an active experiment.

The [execution-lane decision](../architecture/03_the-gate.md) and [native engine](https://github.com/fsantibanezleal/CAOS_SoftQP_Engine) define current support. Browser replay and a file-based local solve remain useful without implying GPU or browser-native optimization.
