# Software design document: SoftQP Studio

Design version 0.01.000. The solver contribution is a hypothesis subject to proof and comparative evaluation.

## Problem and non-goals

Control, robotics, building-energy, and optimization engineers encounter quadratic programs whose selected operational constraints may yield. Solver APIs often make the mathematical meaning of “soft” difficult to inspect: a quadratic violation cost, an exact linear penalty, a weighted two-sided penalty, a group penalty, and an infeasibility-repair objective can return different decisions even when attached to the same interval. Practitioners need to see what is softened, what remains hard, how lower and upper violations are priced, whether the returned point solves that declared objective, and how numerical behavior changes across methods.

SoftQP Studio is a research workbench that lets a reader select a fully specified case, edit supported cost and scenario parameters, solve and compare declared formulations, inspect side-specific violations and residuals, and export a provenance-bearing result. Its offline scientific pipeline is authoritative. The website replays checksummed results; any browser solver is a separately gated lane.

Non-goals:

- A certified controller, safety case, engineering approval, or production control loop.
- A claim that feasibility restoration, fixed elastic penalties, exact penalties, and infeasibility certificates have interchangeable semantics.
- A universal ranking of solvers or transfer of paper timing claims to this product's machine.
- A hosted solver API or collection of user scenarios on a server.
- Client-specific models, proprietary datasets, or unlicensed data redistribution.
- A claim that asymmetric costs, always-feasible optimization, or L1 exactness are new.
- Social-media publication. Required diffusion materials are private repository drafts only.

## Executive brief

Data file: content/executive.json

The sourced bilingual brief and three authored illustrations frame the engineering policy, affected roles, existing methods and acceptance actions.

## Research basis

Research is documented in [the source review](../research.md). It reviews classical explicit lifting, OSQP, the 2025 quadratic-slack ADMM result, the 2026 generalized slack projection paper and its OSQPSlack implementation, DAQP, ElastiQP, PIQP, MPC soft constraints, benchmark protocols, and ICLR 2026 FlexQP/Deep FlexQP.

| Design decision | Research finding | Consequence |
|---|---|---|
| Keep explicit lifting as the classical baseline | It directly represents the declared penalty with variables and constraints and is an independent oracle path. | Run an actual QP implementation and recover/verify physical slacks. |
| Include generalized slack projection | The 2026 paper provides multiple convex penalty families without increasing the principal QP dimension under its assumptions. | Pin the authors' source revision and reproduce compatible penalties. |
| Compare side-specific penalties | DAQP already supports different lower/upper linear and quadratic weights. | Asymmetry alone cannot be presented as the proposed contribution. |
| Include exact restoration semantics | FlexQP is an always-feasible exact L1 elastic method; learned Deep FlexQP reports acceleration. | Treat it as a distinct restoration objective. The official ICLR paper entry inspected on 2026-10-31 exposed no code link; do not claim its results are reproduced. |
| Candidate contribution | Unconditional penalty assumptions in the generalized projection paper exclude non-even penalties. | Test an asymmetric separable convex penalty update in OSQP-style ADMM; novelty remains unproven until the primary-source search and method review are complete. |
| Static-first product | The primary outputs are finite, versioned, reproducible result documents. | GitHub Pages is a candidate only after payload, route, and browser measurements. |


Sources: https://arxiv.org/abs/2610.35631 ; https://osqp.org/docs/solver/ ; https://darnstrom.github.io/daqp/start/advanced/soft ; https://openreview.net/pdf?id=HL3TvE4Afm .

UNVERIFIED: novelty, superiority, complete method coverage, field safety and deployment.

## Sizing and contracts

The current size estimate is a research-grade software package, not a small front-end. The product template provides the app, contract system, pipeline structure, guards, notebook and deployment scaffolding; it does not provide the scientific methods, adapters, fixtures, proofs, data, result matrix, bilingual lessons, manuscript, or UI interaction. Expected workload is XL across method engines and matrix, L across product/app/docs, and L for release evidence. A release is gated by the exact acceptance matrix, not an elapsed-time estimate.

Proposed units with disjoint write ownership after contract freeze:

| Unit | Boundary | Owns |
|---|---|---|
| U1: contracts and case pipeline | schemas and manifests | `data-pipeline/pipeline/io`, schemas and catalog rows, deterministic case registry, splits/seeds, run orchestration, output validation and replay index |
| U2: solver engines and adapters | method API/result | engine build and pinned source provenance, explicit lift, generalized projection, DAQP/FlexQP adapters, AAGSP only after proof gate |
| U3: web and content | static artifacts | six shell pages, app case interaction, comparison/inspection/export, English/Spanish content, accessibility and measured browser gate |
| U4: evidence and curriculum | experiment artifact/notebooks | held-out runner, stats and raw measurements, bilingual notebooks and docs, executive brief, manuscript/report and private post drafts |

The units define module ownership and stable contract seams.

Engine decision: AAGSP extends solver behavior below the UI and should be reusable/testable independently. The current CAOS template forbids an internal product package and requires reusable libraries in separate public package repositories. Therefore the design selects a **separate public solver-engine repository and pinned published Python distribution** if direct extension of OSQPSlack is confirmed as the required route. Working names are `CAOS_SoftQP_Engine` and `softqp`; the public OSQPSlack repo is MIT and its two reviewed pinned submodules include Apache-2.0 license text. PyPI lookups found no JSON records for three candidate names on 2026-10-31; this is not a reservation. Complete nested notice audit, upstream diff review, wheel buildability, ABI support, and exact dependency pins remain pre-creation checks. If no safe, reproducible package route exists, stop and bring a revised SDD; do not bury an unpublished package inside the app. The public app repo remains `CAOS_SoftQP`.

## Technology and versions

The app base is template release `0.14.001` observed in the template review checkout and shell `0.19.1` observed in that template. Both must be rechecked at instantiation and then frozen exactly. Python, Node, solver distributions, benchmark solvers, operating system, compiler, BLAS, notebook runtime, UI dependencies and CI actions are intentionally **not pinned in this pre-approval document**: current primary registry releases and compatible wheels must be measured/verified during the approved instantiate/sizing gate and recorded in the product SDD. Candidate runtime is CPU-only. No GPU requirement is justified. Dependency licensing must be reviewed before inclusion.

## Resources

Design budgets, to be measured and enforced before release; no stage has yet been shown to meet the full-product budget. CPU-only.

| stage | memory | disk | time | where it runs |
|---|---|---|---|---|
| bake | 4 GiB | 2 GiB raw samples | 2 hours | bounded workstation job; reduce batches without discarding required cells |
| training | not applicable until a learned comparator is reproducibly available | no model currently produced | no training currently scheduled | baseline and candidate are deterministic solvers |
| tests | 4 GiB | 2 GiB temporary build | 15 minutes | build system time limit; analytic/lifted suite is a separate narrow measurement |
| build | 2 GiB | 1 GiB dependencies and outputs | 5 minutes | static-site build budget |
| deploy | browser budget 256 MiB | 20 MiB compressed artifacts | initial route 3 seconds under declared QA network | replay-first design acceptance budget |

## Lanes

Offline: native solver and independent lifting with full matrix, validation and checksummed export. Replay: committed artifact documents read by the browser. Live: disabled until native browser packaging, matched-result parity, resource and latency measurements pass; replay parameter selections must never be labeled as a newly solved scenario. No server lane is planned.

## Method ladder

Each promised method is a real executable vertical, not a citation. The final set and compatible cells are fixed in the machine-readable matrix before implementation.

| id | tier | method | acceptance criterion | gate |
|---|---|---|---|---|
| M-1 | classical | Explicitly lifted soft QP solved with pinned OSQP | Same canonical objective, recovered slack and objective agree with an independent high-accuracy oracle within the per-case tolerance; hard rows remain within tolerance. | Contract, oracle, and per-case tests |
| M-2 | sota | Authors' generalized slack projection OSQP implementation | Reproduce supported quadratic, L1, elastic-net and selected grouped cases at the exact source pin; objective, slack, and residual reports validated against lifting. | Provenance/source-pin and method-case matrix gate |
| M-3 | sota | DAQP side-specific weights | Lower/upper linear/quadratic semantics map exactly; only compatible convex cases are compared, and unsupported cases are marked incompatible with reason. | Adapter parity and case compatibility gate |
| M-4 | sota | FlexQP exact L1 feasibility restoration | Reconstruct from the paper only if its algorithm, assumptions and test oracle are independently reviewed; report as restoration, not a substitute for arbitrary fixed penalty objectives. | Mathematical implementation review and oracle gate |
| M-5 | sota | Deep FlexQP | Record paper scope and claims; execute only if official code/weights/data are found and licensing, pinned dependencies and matched cases pass review. No repository link was exposed by the ICLR record at design time. | Source availability/provenance gate; otherwise a documented unavailable comparator, never a fabricated result |
| BS-1 | beyond | AAGSP side-specific generalized projection | Mathematical review passes; independent lifted oracle agrees on all supported cases; preregistered practitioner outcome improves on compatible matched cases without hard-constraint or accuracy regression. | Proof, novelty, adversarial tests, and held-out benchmark gates |

Internal tier words and IDs remain in design/control records only. Product pages, README, notebooks, posts, and manuscripts use method names and the shared terminology rules.

## Cases

Minimum catalog: 12 deterministic, meaningfully distinct cases. All compatible method-by-case cells run and every incompatible cell records a reason. Initial matrix:

| ID | Case | Category | Main evidence |
|---|---|---|---|
| C01 | Single lower-bound undershoot | semantic oracle | lower-side penalty, signed slack, objective |
| C02 | Single upper-bound overshoot | semantic oracle | upper-side penalty, signed slack, objective |
| C03 | Competing lower and upper rows | semantic oracle | side asymmetry and active-set change |
| C04 | Mixed hard and soft rows | hard-row integrity | hard violations, soft trade-off |
| C05 | Grouped penalty case | penalty compatibility | group slack norm versus separable methods |
| C06 | Sparse scaling family, held-out seeds | numerical structure | n, m, nnz, setup/factorization/solve |
| C07 | Semidefinite Hessian with regularized and unregularized variants | numerical structure | assumptions, status, residuals |
| C08 | Ill-conditioned Hessian and row scales | numerical structure | accuracy, iterations, factorization stability |
| C09 | Feasible double-integrator MPC | repeated control | baseline equivalence and warm-start behavior |
| C10 | Disturbance-induced state conflict with hard dynamics/actuator bounds | repeated control | selected state violation, invariant hard constraints |
| C11 | Conflicting safety boundaries | control conflict | restoration versus declared user penalty semantics |
| C12 | Warm-started parameter stream | repeated control | update/factorization reuse, continuity, status |
| C13 | Reproduced two-zone/battery/grid energy case from OSQPSlack source | energy | source-faithful reproduction before variants |
| C14 | Energy comfort/import with distinct side costs | energy | product-specific asymmetric application |
| C15 | Mixed linear/quadratic side-specific penalty | energy/control | exact penalty semantics and solver coverage |

C13 includes the upstream model/data terms under compatible license and preserves attribution; otherwise a documented non-redistributable input reference and checksum is used, with a separately authored model only if the research question remains comparable. No synthetic case may be represented as field data.

## Oracles

Correctness is checked two ways: (1) independent explicit lifting solved to tighter tolerances, with recovered slacks and objective recomputed in original coordinates; (2) KKT/primal/dual residual checks and high-accuracy cross-checks on compatible cases. Hard/equality rows have separate tolerances and can never be counted as soft slack. Penalty decomposition is recomputed outside each solver. Infeasible restoration outputs are not compared by a fixed-penalty objective unless formulations match exactly.

Recorded metrics: objective components, objective gap, primal/dual/KKT residuals, side-specific and aggregate violation, hard-row violations, violated row IDs, status, setup/factorization/update/solve/end-to-end time, iterations, matrix dimensions/nonzeros, peak memory where measurable, warm/cold mode, timeouts/failures, machine/runtime/BLAS thread settings, package/source hashes, seed and tolerance configuration.

Protocol: paired generated problems and held-out seeds declared before final bake; repeated timing samples; pinned machine and dependency environment; thread limits; equivalent termination accuracy; medians and dispersion/uncertainty; preserve raw samples. Report incompatible or failed runs explicitly. No cross-paper timing is used as a product comparison. DAQP, FlexQP and Deep FlexQP are reported only for semantics/availability that can be supported fairly.

## Deploy driver

GitHub Pages is the leading static candidate because the reader replays committed case results and no user scenario needs a server. Selection is conditional on measured build size, route/deep-link behavior, browser memory and payload budgets. If client-side solving fails those budgets, ship replay only. Domain inventory/availability is not yet established; no custom domain is selected. CI runs inexpensive guards/builds; offline scientific matrix is a separately invoked reproducible gate, not run on every push. Deployment acceptance requires live URL checks for version, case/experiment routes, checksums and language/theme behavior.

## Risks and kill criteria

- AAGSP identity/prox/convergence proof fails or duplicates known published work: stop that method and revise the contribution before product creation.
- The required method does not beat relevant baselines: report negative evidence; do not claim beyond-current-method results or release a product claiming the contribution.
- OSQPSlack extension cannot be legally and technically isolated into a reproducible public engine package: stop before repo creation and redesign the ownership route.
- FlexQP reconstruction cannot be validated: mark method-cell unavailable with the exact reason; do not imply reproduced results. Deep FlexQP has the same rule plus model/data provenance.
- Third-party energy case cannot be licensed or reproduced: record exclusion and ensure the authored alternative tests the same declared question.
- App payload or browser computation exceeds measurements: retain offline methods and static replay, disable live execution.
- Solver defaults diverge in tolerance/status: exclude ranking unless matched accuracy is shown.
- Template residue, shallow bilingual material, missing matrix cells, or missing manuscript gates: release blocked.

## ADR fit

Adopt ADR-0057 (scientific app), ADR-0056 (wiki), ADR-0058 (architecture modal), ADR-0069 (full scientific repository), ADR-0070 (Focus workbench), ADR-0071 (viewport and UI), ADR-0074 (cheap CI), ADR-0075 (reviewed pre-code SDD), ADR-0078 (rules in shared template), ADR-0080 (contracts/readiness), ADR-0054 (replay discipline), ADR-0068 (versioning), ADR-0061 only for the separate engine package if confirmed, and applicable content, notebook, method-tier, manuscript, deploy, community and privacy rules. No exception is requested.

| ADR | Rule | Carried by |
|---|---|---|
| ADR-0070 | The App is a case workbench with Focus mode that retains case, method and unit selection. | `frontend/src/workbench/Workbench.tsx`, `npm run gate` |

## Proposed method and exact mathematical boundary

Let the hard QP be

`min_x 1/2 x^T Q x + q^T x` subject to `l <= A x <= u`,

where `Q` is symmetric positive semidefinite. A soft row introduces signed slack `xi` and penalty `Phi(xi)` under `l <= Ax + xi <= u`. For the proposed family, `Phi(xi) = sum_i phi_i(xi_i)`, where each `phi_i` is proper, closed, convex, has its minimum value zero at zero, and may have different positive- and negative-side slopes and curvature. The minimum-at-zero property implies each convex scalar penalty is nondecreasing moving away from zero on either ray.

For one interval `C=[l,u]` and residual `z=Ax`, minimize `phi(xi)` subject to `z+xi in C`. If `z` lies in `C`, `xi=0` is optimal. If `z>u`, feasible `xi` is negative and the optimum is the feasible value closest to zero, `xi=u-z`. If `z<l`, the optimum is `xi=l-z`. Therefore the eliminated cost is `g(z)=phi(Pi_C(z)-z)`, equivalently `phi(-R_C(z))` where `R_C(z)=z-Pi_C(z)`. This uses no evenness assumption; it is specific to coordinate-separable penalties and interval rows. The product must prove the vector value function is closed convex under the catalogued assumptions and check degenerate/infinite interval endpoints.

The generalized projection update candidate is `G(v)=Pi_C(v)+prox_{(phi composed with negation)/rho}(v-Pi_C(v))`, coordinatewise for separable penalties. For asymmetric piecewise elastic-net penalties, define

`phi(xi)=a_plus max(xi,0)+a_minus max(-xi,0)+0.5 b_plus max(xi,0)^2+0.5 b_minus max(-xi,0)^2`,

with all coefficients nonnegative. For `r=v-Pi_C(v)>0`, the returned offset is `max((rho*r-a_minus)/(rho+b_minus),0)`; this is the upper-bound violation branch because the original slack is negative. For `r<0`, it is `-max((rho*abs(r)-a_plus)/(rho+b_plus),0)`. Coefficients and sign conventions are fixed in one mathematical contract and independently tested against scalar minimization and explicit lifting before any engine code is accepted.

This is a derivation candidate, not a novelty result. A derivation sketch and source-level novelty search are recorded in the research dossier; a formal review must still establish the slack-elimination identity, convexity and closedness of the reduced term for all declared endpoints, proximal formula, ADMM assumptions and convergence, handling of hard/equality/fixed/free rows, numerical edge behavior, and prior-art boundary. If those fail, stop implementation of AAGSP and revise the proposed method before any product repository is created. Product release cannot list a protocol or benchmark as the beyond-current-method contribution. A method that fails to beat a relevant baseline remains reported as a negative result; a different method proposal would then be required before a qualified product release.

## Contracts and pipeline boundaries

The product's catalog will have one schema, example, producer check, consumer check, missing-data state, provider, and swap test per boundary. Candidate rows, versions initially `1.0.0`:

| Contract | Payload | Owner / validation |
|---|---|---|
| `case-spec` | Q, q, A, finite/infinite bounds, row kind, units, penalty family and coefficients, case metadata, provenance | case registry validates dimensions, convexity assumptions, finiteness and IDs; engine adapter independently validates accepted input |
| `run-request` | case ID plus typed parameter override, method ID and numerical settings | pipeline producer and method adapter validate against shared schema; reject unknown/NaN/out-of-range, never coerce |
| `run-manifest` | software/source pins, environment, seed/split, solver status, metrics, tolerances, compatibility, timing protocol, artifact hashes | bake validates all fields and artifact existence; reader verifies document and checksums |
| `solution-artifact` | primal/dual solution, signed and side-specific slacks, objective components, residuals, iteration/convergence trace summary | engine emits; independent checker recomputes original-space constraints/objective and validates same schema |
| `experiment-index` | named matrix rows, methods, case refs, status and excluded-cell reasons | experiment aggregator validates exact matrix coverage; web consumer rejects duplicate/missing required cells |
| `readiness` | row-wise state, provenance, missing/stale reasons | pipeline computes; frontend reads; absence never becomes zero or success |
| `export` | portable case, method result, provenance and checksum | export builder validates, schema test loads exported file from clean path |

States use the template vocabulary and explicitly distinguish `missing`, `partial`, `stale`, `provider`, `training` only if applicable, and `available`. A failed solver is a recorded result with failure status, not a missing row. An unsupported method-case pair has `incompatible` plus reason in the matrix, not an omitted cell. A stale artifact never silently renders as current. Schema changes require a version/history row and both producer/consumer tests.

Offline stages: ingest source/registry -> validate -> generate/pin seeds and splits -> solve each compatible method/case/settings -> independent oracle and residual checks -> aggregate held-out statistics -> export immutable artifacts -> validate inventory/checksums -> replay. Browser replay loads committed artifacts only. A browser live lane is optional and only admitted if complete solver code is bundleable, result parity is demonstrated, memory/payload limits pass, and per-case latency is within the measured product budget. No server lane is planned.

## Application, UI and deliverables

Instantiate current `CAOS_PRODUCT_TEMPLATE` exactly, use `@fasl-work/caos-app-shell` pinned to the version current at scaffold time, and follow the current template six-route contract: App, Introduction, Methodology, Implementation, Experiments, Benchmark. English and Spanish plus light and dark themes are release requirements. App opens on one selected case, provides real supported parameter edits, solve/compare, visible hard/soft row policy, side-specific violation chart, convergence/residual inspection and portable export. Cross-case selection and result matrices belong in Experiments/Benchmark. The page viewport is the app; keyboard access, focus behavior, empty/error/stale/incompatible states and responsive layouts are part of the measured gate.

Architecture modal: five bilingual, theme-aware tabs with complete product architecture and data-flow content. The `docs/` wiki is maintained in the same implementation units and contains method derivations, assumptions, API/contracts, reproducibility, licensing, data provenance, limitations, operations, and contribution guidance. Bilingual notebooks run from simple penalty semantics to published-method comparison and AAGSP falsification; numerical output is executed and checked, never placeholders. Final technical report is required. A separate proposed-method manuscript is prepared only if the method is correct, reproducible and scientifically interesting; otherwise the technical report records negative/inconclusive evidence. Manuscript authorship is reviewed explicitly before publication.

Six diffusion drafts are required by product coverage: executive problem context, two distinct notebook lessons, method/research story, and two further product areas. They remain unsubmitted files in the repository under the user's no-publication instruction.

## Requirements and release gates

Detailed EARS requirements and validation rows are created in the product repo from this accepted SDD before any feature code. Every requirement must point to an executable test/check or a named reproducible review artifact. Minimum feature groups and gates:

| Requirement group | Required proof |
|---|---|
| Problem context | executive schema, source/claim checks, EN/ES content and illustration audit |
| Case/penalty contract | adversarial schema and scalar/vector penalty oracle tests |
| Methods | each method acceptance gate and exact method-case coverage |
| Scientific pipeline | full offline ingest-to-export replay, checksums and fresh-environment run |
| Numerical correctness | independent objective/slack recomputation, KKT/hard-row checks, failure cases |
| Statistical evidence | preregistered held-out paired matrix, repeated runs and report completeness |
| Web app | shell gate, keyboard/focus/responsive/EN-ES/light-dark matrix and real interactions |
| Documentation/curriculum | notebook content audit and fresh-kernel execution in both languages, deep sourced wiki |
| Provenance/community | dependency/license notices, citations, data/license audit, template residue and content guards |
| Delivery | release manifest, artifact version/hash, deployment/live smoke and Zenodo report relation |

No requirement is accepted solely because it renders, builds, or returns HTTP 200. No full release is claimed until all method and case gates pass; no superiority claim until the held-out acceptance criterion passes.

## Beyond the state of the art

BS-1: AAGSP tests the hypothesis that a side-specific separable elastic penalty update can preserve OSQP's original KKT dimensions while improving setup/solve work against matched explicit lifting in a practitioner-relevant regime. This is a proposed method awaiting the complete held-out comparison. The native implementation must include projection, objective, dual conjugate, scaling and recession behavior. An independent explicit-lift oracle, hard-row residual checks and paired measurements refute or support it. It cannot be described as novel or superior before the evidence and prior-art review justify that claim.

Primary sources: https://arxiv.org/abs/2610.35631 ; https://osqp.org/docs/solver/ ; https://darnstrom.github.io/daqp/start/advanced/soft ; https://openreview.net/pdf?id=HL3TvE4Afm .

UNVERIFIED: novelty, superiority, full case coverage, deployment and operational value; all require the declared gates.

The Methodology page uses the documented `method-learned` floor waiver: the implemented method set is deterministic convex optimization and has no trained parameter policy. This does not waive any method implementation, comparison, mathematical-depth or executive-brief requirement. Deep FlexQP remains an availability-gated related method with distinct restoration semantics.
