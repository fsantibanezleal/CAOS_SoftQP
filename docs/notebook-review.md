# Independent curriculum review

Date: 2026-11-01. Status: all eight lessons pass. A separate reviewer agent, authorized by the owner, read the sources, all fourteen saved figures and the relevant generators, predictors, diagnostics and method adapters. The reviewer did not write or modify the notebooks. This is a curriculum review, not external peer review of a research contribution.

## Findings and corrections

- Spanish lessons 03 and 04 initially displayed raw English method identifiers as figure ticks or legend labels. Separate Spanish display names now preserve the backend identifiers while translating the figures. The corrected saved figures were inspected and passed.
- English and Spanish lesson 02 initially placed actuator samples at post-control state times using midpoint steps. Controls now use interval edges from 0 to 4 seconds with `stairs`, consistent with the declared dynamics and a zero-order hold. Each horizon has its own relative time origin; state timestamps remain at interval ends. Both corrected saved figures were inspected and passed.

## Per-lesson verdicts

| Level | English | Spanish | Evidence |
|---|---|---|---|
| 1, side prices | Pass | Pass | Executed scalar optima, original objective and cost interpretation agree. |
| 2, control integrity | Pass | Pass | Hard/soft row policy, condensed dynamics, first prediction, KKT diagnostic and repeated update agree; control-interval figures corrected. |
| 3, published methods | Pass | Pass | Equivalent symmetric-elastic and pure-L1 comparisons actually execute supported methods; Spanish figure display names corrected. |
| 4, computational claim | Pass | Pass | The complete raw endpoint is independently recomputed, preserving the failed 10% criterion and its seed-cluster interval; Spanish representation labels corrected. |

The independent calculation retained 21888 raw observations including warm-ups, 168 accepted primary pairs and six seed clusters. Median relative reduction is 0.499839%, with a 95% seed-cluster interval of [-3.291967%,3.944835%]. The negative result is unchanged.

All eight notebooks pass static checks and a full copied-repository fresh-kernel check with unchanged outputs. An additional consumer check replaced the notebook environment's VCS-installed engine with the public PyPI 0.1.0 wheel and again reproduced every notebook's outputs without changing their bytes. The pipeline's historical engine remains pinned separately for the frozen computational experiment.
