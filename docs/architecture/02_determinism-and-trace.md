# Reproducibility, provenance and timing

Input generation is deterministic from its declared seed and structural parameters. The catalog seed is distinct from the campaign's development, held-out and robustness splits. A conditioning sweep keeps A, q, bounds and costs fixed within a seed and changes only the Hessian diagonal. A canonical catalog example is not automatically one member of that controlled sweep.

Solver output has numerical tolerances and backend-specific stopping behavior. Elapsed time, operating-system resource observations and native setup counters are measurements, not deterministic input functions. Repeating a bake can therefore change exported bytes even when decisions agree within tolerance. Reproducibility means recovering the declared computation and its accuracy, not promising identical wall-clock samples.

Every case file is serialized to explicit UTF-8 bytes and indexed by SHA-256. Experimental JSON, JSONL and CSV use LF on Windows and Linux so Git's text normalization cannot invalidate recorded digests. The export verifier checks file sizes and digests, validates each raw trial, checks the complete instance/method/repetition denominator and recomputes aggregate summaries. A duplicate or missing observation fails even if someone updates its file digest.

Environment records contain Python and package versions, platform information, exact engine revision, clean-source state and the loaded native binary hash. They omit local paths, hostnames and credential-bearing URLs. The frozen campaign also records the protocol digest and numerical runner source hashes. Editable-checkout revision discovery verifies the source layout before consulting Git, preventing an unrelated ancestor repository from being reported as engine provenance.

Cold end-to-end time includes input validation, formulation construction, setup, solve and original-space evaluation. It excludes import, input generation and export. Warm observations include vector validation/update and solve/evaluation; initial workspace setup is separate. Native setup includes linear-system preparation, so isolated factorization time is uninstrumented. Worker RSS is process-level evidence, not a per-method native allocation peak.

The [frozen protocol](../design/experiments-v1.json) fixes seeds, tolerances, repetition count, random ordering, resource limits and the endpoint. Timing results must retain failures and their denominators.
