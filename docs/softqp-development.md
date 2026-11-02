# Scientific development and local execution

SoftQP Studio executes optimization with the separately versioned [SoftQP engine](https://github.com/fsantibanezleal/CAOS_SoftQP_Engine). The ordinary development and notebook requirements install published `softqp==0.1.0` from PyPI. CPython 3.12 wheels are available for Windows x86-64 and Linux x86-64, so those installations do not need a C/C++ compiler or CMake. Building the source archive on another supported target requires the native build tools and its own validation.

```bash
python -m pip install -r requirements-softqp.txt
python -m pytest tests/test_softqp_matrix.py tests/test_softqp_contracts.py tests/test_softqp_requests.py -q
python data-pipeline/run_softqp.py --output "$CAOS_TEMP_ROOT/softqp-development"
```

An explicit output directory prevents exploratory runs from replacing committed records. The fifteen-case development matrix executes explicit lifting, published generalized projection, the separable asymmetric extension and DAQP on compatible formulations. All cells retain available, failed or incompatible states. DAQP requires positive definite curvature and positive quadratic soft costs; it inserts no regularizer. Pure L1 edits additionally run a paper-equation FlexQP reconstruction and published ElastiQP 0.2.0; the learned Deep FlexQP policy is not implemented.

The building model is adapted from OSQPSlack under MIT. Attribution is in `data-pipeline/pipeline/energy_reference.py` and `data/licenses/OSQPSlack-MIT.txt`. C13 preserves the original mixed penalties. C14 and C15 replace them with declared authored separable side costs.

## Edit costs, solve locally, inspect

1. Open the App, select a separable case, and expand **Edit costs and solve locally**.
2. Set lower, upper and quadratic multipliers between 0.01 and 100 (the quadratic factor also allows zero). Lower/upper factors multiply the corresponding linear and quadratic soft costs; the quadratic factor further multiplies both quadratic sides. Hard rows are unchanged. A zero quadratic factor explicitly chooses a pure L1 variant and executes the compatible fixed-parameter FlexQP reconstruction and published ElastiQP reference, with reasons for incompatible cells.
3. Download the solve request. In a checkout matching the displayed inventory, run:

   ```bash
   python data-pipeline/run_request.py "$CAOS_TEMP_ROOT/C01-request.json" --output "$CAOS_TEMP_ROOT/C01-result.json"
   ```

4. Import the local result in the App. It checks the request, unchanged matrices and row policy, schema, original objective, side violations and comparison gaps before displaying it. Restore the original record with its dedicated control.

The CLI verifies the base artifact digest and its serialized matrices against the current source catalog before applying edits. A stale request must be regenerated against matching data; it is never silently rebased. Coupled penalties in C05 and C13 are not converted to separable costs. The browser sends no request or result to a server.

## Evidence boundaries

The browser replays committed or locally imported native records. A browser solver has not been enabled. The fixture source is isolated: build with `VITE_SOFTQP_SOURCE=fixture` for its C01-only inventory; the interface labels that provider explicitly. The actual loader and checksum checks are tested for both sources.

The committed catalog timings are individual observations. The separate complete campaign has 456 controlled instances and preserves all repeated observations. Its registered timing hypothesis is negative: median reduction 0.50%, 95% interval -3.29% to 3.94%, against the faster matched baseline. The source, raw evidence and resource scope are in [measured resources](design/measured-resources.md).

C12 has a complete 32-frame paired stream. Cold/warm timings use identical independently driven state inputs; initial workspace setup is separate. Its record contains 192 accepted observations and 64 explicit incompatibilities.

## Registered experiment workflow

The frozen runner requires the exact clean source revision in `docs/design/experiments-v1.json`. Reproduce that historical environment explicitly in a separate checkout/environment with engine revision `d0c69ed974d577ba02adbd4806332270d9425651`; a public package version or later packaging-only commit cannot substitute for its exact revision. The ordinary current requirements install the published wheel and do not reconstruct this historical source environment. The source build requires a C/C++ compiler and CMake.

```bash
python data-pipeline/run_experiments.py campaign --output FRESH_OUTPUT
python data-pipeline/run_experiments.py publish --campaign-input FRESH_OUTPUT --output data/derived/experiments
python scripts/check_documents.py
```

Publication checks raw sizes/digests, schemas, the complete instance/method/repetition matrix and summaries recomputed from the raw JSONL. Missing or duplicate observations fail even with a changed digest. CSV retains readable scalar fields; JSONL is the complete per-trial record. LF serialization preserves digests across Windows and Git.

The six documentation routes and one-case workbench consume those records. A complete experiment does not establish global novelty or accepted release. The approved plan's strict stop/revise gate applies to the failed candidate hypothesis; notebook/report/package preparation and full product QA remain separate work.

The additional directional-group-peak lesson uses pipeline.coupled_lessons.run_comparison, an actual separate external SDK2 worker. Its schema, installed public SDK fingerprints, source/input identities, original-space checks, direct runtime admission and owned process deadlines are documented in docs/design/features/coupled-lessons/design.md. It runs only instructional two-variable comparisons, not either registered timing campaign. The kernel retains its original SDK1 pins.
