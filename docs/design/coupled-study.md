# Directional coupled peak study

This is a separate prospective study. The original preregistration, 456-instance data, negative timing result, report and notebook outputs remain unchanged. The coupled study has no accepted timing result or qualified app release. Its JSON protocol stays locked until independent source/protocol review and public SDK provenance are recorded and committed.

The narrow question is whether preserving original interval rows helps a complete repeated-forecast operation compared with exact existing formulations. Directional expressibility, weighted threshold projections and relaxed ADMM are established methods. The closest comparator is the published symmetric grouped projection after directional one-sided row splitting; compact stock-OSQP epigraph and direct/proximal DAQP policies are also registered. The original failed 10% result cannot be replaced by a favourable subset of the new study.

## Environment and data

Use a separate CPython 3.12 environment on supported Windows x64 or Linux x86_64:

```powershell
py -3.12 -m venv .venv-coupled
.venv-coupled/Scripts/python -m pip install --index-url https://pypi.org/simple -r experiments/coupled-v1/requirements.txt
```

All inputs are generated from committed formulas and preregistered seeds. No external dataset, private records, API key or downloaded operational building data is required. The sparse cases have hard coordinate bounds and disjoint directional groups. The hourly thermal cases use an original RC forecast model with hard initial conditions, dynamics and heater-energy limits and one comfort peak per zone across the horizon. Their coefficients and prices are synthetic; these are forecasts, not measured building performance or closed-loop control trajectories. Every variable, row and objective coefficient has an explicit unit map in the canonical batch.

The independent profile lives under `experiments/coupled-v1/`: the product and reviewed legacy notebooks retain their existing 0.1.0 dependency declarations. `scripts/check_coupled_requirements.py` separately checks every study pin against the protocol, and runtime checks verify the installed public 0.2.0 wheel and all dependency versions. This preserves the historical environments while preventing dependency drift in the new experiment.

The conventional horizon/dynamics organization follows [OSQP's MPC formulation](https://osqp.org/docs/examples/mpc.html). The directional row-split comparator implements an existing formulation of [generalized slack projection](https://arxiv.org/html/2610.35631v1). DAQP policies follow its [documented proximal parameters and candidate statuses](https://darnstrom.github.io/daqp/parameters/); no permanent Hessian shift changes the objective.

## Frozen boundaries

One observation includes preparation/factorization, all 32 vector updates and solves, physical recovery and independent accuracy checks. Generation, process/library startup and evidence serialization are excluded for every method. All competing compiled libraries are preloaded symmetrically before the inner timer. A separate process supervises each observation, including startup and serialization, using trial/campaign deadlines and sampled current/high-water RSS. Large results use files rather than blocking bulk pipes.

Acceptance independently recomputes original objective and KKT quantities. It checks raw and repaired stationarity, each soft group's Fenchel gap and each hard row's complementarity separately. Signed cross-row cancellation cannot qualify a solution. Every frame must pass; backend candidate flags alone do not pass the gate.

The primary inventory is all 144 heldout instances across six seeds and both complete families. Missing/failed compatible observations receive the prespecified failed-pair treatment and prevent qualification. Compatibility is derived from registered problem semantics, never trusted from an output flag. Warmups, failures, timeouts and incompatible cells remain in the raw journal. All controls and baselines are fixed without timing-based tuning.

The separate registration manifest pins the exact protocol, source map and accepted independent review. Runtime verification checks committed source cleanliness, dependency versions, public SDK Python sources and native binary identities. Editing a setting, seed, schema or source invalidates the freeze. The wrapper refuses an unregistered draft before generating heldout problems.

## Execution and verification

After registration has passed and been committed remotely:

```powershell
.venv-coupled/Scripts/python data-pipeline/run_coupled_study.py --check-freeze
.venv-coupled/Scripts/python data-pipeline/run_coupled_study.py --split development --output output/coupled-development-v1
.venv-coupled/Scripts/python data-pipeline/run_coupled_study.py --split heldout --output output/coupled-heldout-v1
.venv-coupled/Scripts/python data-pipeline/run_coupled_study.py --split robustness --output output/coupled-robustness-v1
.venv-coupled/Scripts/python data-pipeline/run_coupled_study.py --validate-output --output output/coupled-heldout-v1
```

Each output directory must be new. It contains the protocol snapshot, canonical input batches, full oracle/method JSONL, exact method CSV, index and independent replay validation. Schemas version the batch, observation and index boundaries. The consumer verifies checksums, full inventories, original-space accepted solutions, counts, CSV correspondence and the complete primary analysis. An interrupted directory remains evidence and is never overwritten as a successful run.

The public 0.2 SDK is an engineering release. Companion-app research qualification still requires the preregistered outcome, product integration, source promotion, deployment/live proof and owner acceptance. A negative result remains negative.
