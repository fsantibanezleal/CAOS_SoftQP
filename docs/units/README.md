# Physical quantities and dimensional constants

`float-constants.json` records each float AST occurrence, its enclosing statement,
quantity, unit and rationale across every owned `data-pipeline/**/*.py` module.
`python scripts/check_unit_constants.py` imports no numerical code. A new or renamed
module, changed literal/context, absent annotation or stale entry fails. Review the
inventory diff before accepting a change; the checker cannot judge whether a written
unit is scientifically correct.

The abstract QP families use dimensionless coordinates and stated objective units.
Control uses position m, velocity m/s, acceleration m/s² and sample time s. Its
tracking/control weights have reciprocal squared physical units. Energy uses kW,
kWh, degC and h; temperature differences use delta-degC. The registered hourly coupled thermal family uses heater energy in kWh, dimensionless directional severity factors and a temperature-valued peak in degC; its linear and quadratic prices have objective-unit/degC and objective-unit/degC^2. This differs from the new teaching example, where inverse-metre directional scales give a dimensionless peak and prices in objective units. Both choices are valid when their distinct source unit maps are preserved. Zero
structural coefficients carry the corresponding row/column-compatible unit.

Historical numerical criteria are fixed in their original canonical coordinates.
An absolute backend or hard-row tolerance has that coordinate's unit; a normalized
relative discrepancy is dimensionless. The mixed study formulas use numerical
normalization floors of one in those declared coordinates. They do not establish
invariance under arbitrary changes of physical coordinates. No frozen constant or
acceptance threshold was changed to add this inventory.

The runtime checks recompute decisions and costs against the actual authored source
problem and original row metadata; they never force an optimization answer into a
unit interval or reject an intentional soft departure as an invalid prediction.
The independent double-integrator test uses the real authored condensed model and
nonzero controls, reconstructs physical predictions and checks metre/second to
centimetre/millisecond covariance. Omitted time and acceleration conversions each
fail separately. The advanced directional lesson separately demonstrates reciprocal
row/bound/scale conversion of an actual solved shared-peak objective.

The public SDK remains a separately versioned dependency with wheel/source/native
fingerprints and original-space semantic checks. It is not relabeled as app-owned
code or modified to add inventory comments.

In general, [directional scale]=[group peak]/[row departure], [linear price]=[objective]/[peak], and [quadratic price]=[objective]/[peak]^2. Selecting a dimensionless peak is a modeling choice, not a universal property of shared-peak penalties.
