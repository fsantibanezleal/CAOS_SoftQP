# Design: physical covariance and reviewed numerical constants

This is the current dimensional design of the existing numerical code. It is a retrospective reconciliation, not a claim of an earlier inventory review. The objective is to catch a numerically plausible answer expressed in the wrong coordinates without changing either frozen scientific study or imposing an inappropriate universal prediction range on optimization decisions.

## Two complementary boundaries

`scripts/check_unit_constants.py` examines all owned Python modules below `data-pipeline/` through the AST. `collect` records module discovery, the position and literal value of each float, its statement expression and a hash of the statement AST without source attributes. `docs/units/float-constants.json` supplies the reviewed quantity, unit and rationale beside those identities. `findings` refuses new, removed, moved or altered occurrences, changed module discovery and absent unit declarations.

The inventory never imports the numerical source or rewrites it to add comments. This matters for immutable study code: changing that source merely to annotate units would invalidate scientific registration. The public engine remains a separately pinned dependency with its own byte/source admission; this inventory governs the application-owned numerical layer rather than claiming to review another package by scanning its installed environment.

An AST entry is not a physical oracle. `tests/test_physical_units.py` therefore also challenges the actual double-integrator predictor and the condensed model's state rows. Position, velocity, acceleration and time convert together. If metres become centimetres and seconds become milliseconds, velocity and acceleration require their corresponding reciprocal time factors. Applying only the distance factor or omitting the time factor changes the predicted physical path and must fail the independent control.

## Original-space result admission

`pipeline.control.predict_states` returns post-control positions and velocities from the supplied controls without clipping them. The original model, sampling period and actuator meaning come from `pipeline.softqp_cases.mpc`. For each predicted interval, acceleration acts across the full interval and the state is timestamped at its end. A small solver residual cannot repair a wrong sampling period or a mislabeled row.

`scripts/local/softqp_adapter.py` checks the produced case matrix against the authored inputs and original numerical tolerances before local artifact promotion. The adapter independently recomputes original objective and departures; a claimed hard residual from a JSON document is not an authority. `tests/test_local_softqp_admission.py` plants rehashed incomplete or semantically wrong records and tests original coefficient/settings parity. The case-result schema and catalog retain row unit, hard/soft mask and metric-vector cardinality at the producer/consumer boundary.

This product deliberately has no global [0,1] outcome restriction. A soft-QP optimizer may be outside its preferred interval by design, and normalized dimensionless examples are not field measurements. Hard-row error is checked independently of soft departures. Physical aggregates require compatible units; position, velocity and acceleration are displayed separately. Numerical acceptance bands remain those of the existing scientific problem, not widened to admit a converted result.

## Failure behavior and rejected alternatives

An unreviewed float or renamed module is an inventory failure, not a request to regenerate the manifest automatically. Wrong or absent physical metadata is a result-admission failure even when a digest has been recomputed. An unsupported unit conversion remains unsupported until the problem coefficients, row bounds, prices and interpretation all transform consistently.

A comment-only inventory was rejected because it cannot bind a declaration to the actual numerical occurrence. A single aggregate relative residual was rejected because errors with different physical dimensions can cancel or be hidden by normalization. Rebuilding the study to produce a superficially better units report was rejected because dimensional review must preserve the registered authorities.

PU-001 maps to the float-inventory adversary, PU-002 to the independent control covariance adversary, and PU-003 to original-space local admission. [Validation](validation.md) names their actual cases; [tasks](tasks.md) orders discovery, covariance and result checks. Passing these controls supports the stated model's dimensional consistency; it does not certify a plant or establish operational safety.
