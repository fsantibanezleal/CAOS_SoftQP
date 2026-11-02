# Design: directional coupled-penalty computation

## Boundary and ownership

The public engine distribution implements directional group penalties and reusable
workspaces. The offline computation generates canonical forecast batches, supervises
isolated oracle/method observations, independently evaluates original-space numerical
quantities, exports the complete raw journal and CSV, then recomputes the registered
paired outcome. The three registered contract schemas remain unchanged.

Batch, observation and complete-computation boundaries are defined by the catalog's
`softqp-coupled-batch`, `softqp-coupled-observation` and `softqp-coupled-campaign` rows.
The batch encode/decode checks cover the first boundary. The actual producer-journal
round trip and hostile replay checks cover the latter two. Schema-valid examples
demonstrate shape only and cannot establish a completed computation.

## Execution and failure semantics

The dedicated environment and exact source/protocol registration are prerequisites
for execution. The historical product environment is separate. A candidate result
must satisfy the original-space accuracy policy. An iteration limit without returned
vectors is an unsuccessful batch, not a valid but inaccurate optimum. A timed-out
worker supplies no completed solution. Failed common oracles invalidate their paired
comparison without changing the model's compatibility declaration.

The timed operation includes owned validation, setup, all forecast updates and
solves, physical recovery and independent checks. Setup is reused only within an
observation. No failed pair may disappear from the primary population.

## Deployment readiness

This lane runs offline. Its full evidence is distributed separately and is not a
declared coupled-study replay source in the current app artifact root. Readiness
must therefore report these three research-artifact rows as missing, with that
reason. The implementation's presence, a schema example, a test fixture or an archive
link must not turn them into available deployed evidence. A future replay adapter
requires its own contract, complete selected-root identity validation and tests.

## Mathematical and scientific scope

The coupled model is directional linear-quadratic group peaks on original interval
rows. Hard rows remain hard. Coordinate-contraction monotonicity supports box slack
elimination; the metric proximal identity requires a strictly positive diagonal
metric. Fixed relaxation is restricted to its finite saddle-point assumptions.
Existing row-split and compact epigraph formulations remain exact comparators.

The original separable and subsequent coupled predictions both failed their frozen
performance criteria. Their data, source snapshots and endpoints remain distinct.
Document and interface corrections cannot upgrade either prediction.
