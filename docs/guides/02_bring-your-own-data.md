# Supply an original quadratic program

The standalone specification serializes P and A as CSC arrays with shape, data, indices and indptr. The matrix P is fully symmetric in the public contract; passing only its upper triangle is a backend optimization, not the input convention. q, lower and upper have original dimensions. JSON null denotes an absent interval side and decodes to the appropriate signed infinity.

Every row has a boolean hard/soft policy and four nonnegative finite coefficients. Prices on hard rows are not a mechanism to soften them. A purely linear soft side uses zero quadratic price; a zero linear price is not replaced with a hidden backend default. Validate row units before comparing physical violations across a supplied model.

Use `pipeline.io.contract.decode_problem` from scripts after adding `data-pipeline` to the Python module path. It checks CSC offsets, lengths, unique sorted row indices, numeric types, finite values, consistent dimensions, valid intervals and convexity. `softqp.solvers.solve` then applies method-specific compatibility rules. The scientific contract is in `docs/contracts/schemas/softqp-case-spec.schema.json` and its executable example is in `docs/contracts/examples/softqp-case-spec.json`.

The public workbench's local editor currently consumes registered case digests, not arbitrary uploaded matrices. This bounded request contract prevents an imported result from silently changing a declared case. To add a new public case, implement its generator, bilingual physical row metadata, independent oracle checks, case page and contract/deployment export together. Do not invent a successful placeholder for a missing dataset.
