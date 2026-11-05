# Worked SoftQP notebooks

The notebook set teaches the optimization methods through actual public package calls, equations and interpreted results. It is not a pipeline launcher, a validation suite or a viewer of baked JSON. The [English index](../../notebooks/en/README.md) and [Spanish index](../../notebooks/es/README.md) share five relative paths. The [coverage map](../../notebooks/coverage.json) connects the entire declared tool to those lessons.

## The five questions

| Lesson | Method and question | Actual input and result |
|---|---|---|
| Scalar prices | How do separate lower and upper costs move a convex optimum? | Authored scalar interval cases; package solutions, original objective and active-side departure; raw objective and penalty sensitivity figures |
| Control integrity | Can a condensed controller recover from a state conflict while preserving hard actuator rows? | Authored controller state/dynamics and actuator limits; hard/soft row masks, independent original-space evaluation, local request/import and common C12 stream semantics |
| Published implementations | Which methods represent the same requested objective? | Matched inputs passed to explicit lifting, generalized projection, DAQP, FlexQP and ElastiQP within their actual assumptions; incompatible formulations remain explicit |
| Side-specific projection | How do asymmetric prices affect computation and the registered paired finding? | Real asymmetric and lifted package calls, controlled Hessian conditioning, original-space errors and the complete frozen primary endpoint |
| Directional peaks | How do a shared directional price and reciprocal row-unit conversion affect the solution? | A guarded SDK2 call to native, epigraph and row-split methods; quadratic incompatibility, directional policy sweep, physical covariance and the separately accepted negative study summary |

A result table is read immediately after the cell that computes it. A figure states its axes and units and is followed by an explanation of the observed regime, what cannot be inferred and what follows. Fresh educational solves are not additional observations in either registered timing campaign. The original 456-instance result and directional 210-instance study retain their inputs, populations and negative conclusions.

## Environment and source boundaries

Use Python 3.12 and the exact ordinary requirements in `notebooks/requirements.txt`. The ordinary lessons use the published `softqp==0.1.0` distribution. The directional lesson keeps that kernel and calls the separately pinned `softqp==0.2.0` teaching environment through the existing guarded process boundary. It never replaces the ordinary kernel package or recreates the solver inside a notebook. The setup cell prints package versions; installation instructions are explanatory shell blocks, never notebook execution cells.

The ordinary runtime is the external target of `.venv-notebooks`. Set the external temporary root in `CAOS_TEMP_ROOT`; on Windows set `TEMP` and `TMP` to that same task root so Jupyter connection files also stay outside the repository and system temporary directory. Set `SOFTQP_COUPLED_PYTHON` to the independently provisioned direct SDK2 interpreter for the final lesson. Its admitted source/package fingerprints, isolated startup, bounded output and owned-tree cleanup remain mandatory. The teaching caller allows180 seconds for complete cold startup, imports and the three-method solve; this does not change a registered campaign deadline or performance claim.

From the repository root:

```bash
python -m pip install -r notebooks/requirements.txt
python scripts/run_notebooks.py
python scripts/check_notebooks.py
python scripts/check_notebooks.py --pypi
python scripts/run_notebooks.py --check --tmp "$CAOS_TEMP_ROOT"
```

To work on one lesson, add `--only notebooks/en/01-soft-constraint-decisions/02-preserving-control-integrity.ipynb` to the runner. It executes a fresh kernel, strips volatile metadata and is the only writer of stored outputs. The copied `--check` workflow executes an external copy and compares its complete normalized notebook with the committed version; success is separate from substantive scientific review.

## How a lesson explains a method

The first Markdown cell states a unique question, level, prerequisites and expected reading time. The ordered second-level sections are Objectives, Setup, Data, Method, Comparison when required, Evidence for a proposed method, Results, Exercises, Summary and References. The Spanish equivalents follow the same order. In Spanish it is a notebook, never a translated name for a paper notebook.

Before every code cell, explain the purpose, equation and expected intermediate result. Every cell contains a meaningful comment. One concept belongs in a cell, with at most30 logic lines and120 characters per line; semicolon-packed statements are not a shortcut. Setup contains imports, version checks and readers in one place. Every text JSON/JSONL reader explicitly uses UTF-8, so Spanish field descriptions survive Windows execution unchanged.

The method section defines symbols, units, assumptions and the governing equations with primary citations. For scalar pricing, distinguish the original quadratic objective from the separate lower/upper linear and half-quadratic penalties. For control, identify the condensed state map and the hard actuator mask before solving. For comparison, ensure the objective and original row policies actually match before comparing numbers. For directional groups, define the shared peak, directional scales, positive diagonal metric and original-space recovery before discussing a numerical result.

From level 2, a third-level Sensitivity or Limits section changes a meaningful parameter or input and shows the regime where behavior changes or the method is unsupported. A separate Using your own data section teaches the actual sparse input schema, field meanings, package call, output interpretation and checks. Hard rows cannot be made soft to obtain a favorable answer. Infinite endpoints, zero prices, unsupported grouped costs and infeasible restoration retain their distinct meanings.

A level 3 lesson executes the published methods on the same data through the actual package implementations and compares the objective, error and compatibility numerically and graphically. A level 4 lesson derives its proposed update, states the hypothesis, distinguishes instructional observations from the frozen study, presents uncertainty honestly and preserves a negative result. Internal method classification identifiers stay in metadata/design only; headings and prose name each method.

## Measured floors and independent review

| Per notebook | Fundamentals | Levels 2 through4 |
|---|---|---|
| Explanatory prose outside Setup, Data and References | At least 1000 words | At least 1500 words |
| Actual image-output figures | At least 2 | At least 3 |
| Display equations in Markdown | At least 1 | At least 2 |
| Primary references with DOI or stable URL | At least 3 | At least 4 |
| Genuine package/pipeline method-call cells | At least 3 | At least 5 |
| Interpretation immediately after each figure | At least 40 words | At least 40 words |
| Sensitivity/limits and own-data third-level sections | As useful to the introductory question | Both mandatory |

No generic padding, shared long sentences, fabricated figures or notebook-defined package methods are accepted. At most one reproduction check belongs in a lesson. A question that only says run, validate, reproduce or inspect an artifact is not a teaching question. These are floors: a long notebook can still fail if its mathematics, API use or interpretation is wrong.

A reader other than the writer reads every changed lesson and every output figure before release. Review covers the derivation, real package calls, exact input/contract semantics, sensitivity, own-data extension and correspondence between figures and conclusions. A static pass, a successful kernel run and an author report each establish only their own check. The current content checker and the older structural guard both apply.

## Cover the whole declared tool

`notebooks/coverage.json` maps each of the seven executable method rows to a level 2-or-higher lesson. All eighteen catalog contracts map to a lesson that reads or explains their concrete fields, units, producer/consumer and missing-data behavior. Fixtures are labelled examples, never recorded observations. The five real pipeline responsibilities are validate, assemble, solve, evaluate and export; stream, campaign analysis, readiness and the isolated SDK2 boundary are also taught where they arise. There is no invented training or learned-checkpoint stage.

The map is an index to actual teaching, not permission to add an identifier to any notebook. Independent review checks the referenced cells against the implementation and catalog. The source schemas, external runtime and frozen numerical evidence retain their own validation gates. A notebook does not authorize a scientific campaign, deployment or publication merely by importing their modules.
