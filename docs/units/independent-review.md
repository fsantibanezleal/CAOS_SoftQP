# Independent physical-unit correction review

Decision: **ACCEPT_SCOPED_PHYSICAL_UNIT_INVENTORY_AND_COVARIANCE_CONTROLS**. This is a portable summary of the independent non-author review. Detailed original findings, test receipts and source identities remain in the coordination repository.

The current [inventory](float-constants.json), SHA256 `a795c8cfa4004b3c036cf80157db499cae8d8613caf1d86ca1a3d0b8908302ce`, binds251 float AST occurrences across44 owned numerical modules. The actual checker passes; added/stale/changed/renamed source and missing annotations fail. Two actual independently run packaged controls passed, covering inventory adversaries and nonzero-control physical covariance. Five additional independent static controls passed with an unchanged positive.

The double-integrator control uses the actual authored condensed MPC model and an independently reconstructed trajectory. Metres/seconds to centimetres/milliseconds converts position by100, velocity by0.1, acceleration by0.0001 and time by1000. Separate omitted-time and omitted-acceleration conversions fail. It does not solve or regenerate either registered scientific study.

The reviewer required corrections to mixed-expression literal annotations and the registered thermal family. The latter retains heater energy in kWh, dimensionless directional severity, peak in degC, linear price in objective/degC and heater curvature in objective/kWh². This differs from the teaching case's inverse-metre scales and dimensionless peak. The [README](README.md) states the general dimensional rules and preserves these distinct source unit maps.

An AST inventory proves complete declared float coverage, not a universal unit type system or automatic scientific correctness. Historical coordinate-specific normalization floors and tolerances remain unchanged. The public SDK has separate public-wheel fingerprints rather than app-owned literal annotations. All17 frozen source hashes and eight historical notebook byte identities remained unchanged. Full product regression, deployment and scientific qualification are separate gates; both registered improvement criteria remain unestablished.
