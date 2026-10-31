# SoftQP Studio domain research

Date: 2026-10-31
Status: source review supporting the product design. Candidate method claims remain subject to evaluation.

## Research question and scope

Assess whether a public CAOS scientific app based on OSQP and soft-constrained quadratic programs can make a technically defensible contribution beyond the October 2026 generalized slack projection paper. Review the paper, its reproducibility repository and solver implementation, classical lifted formulations, current solvers that support soft constraints, application use cases, benchmark practice, and limitations. This dossier records a candidate direction, not a novelty or performance claim.

## Primary sources reviewed

1. Schwan, Lew, Plancher, *Efficient ADMM for Soft-Constrained Quadratic Programs via Generalized Slack Projections*, arXiv:2610.35631v1, submitted 2026-10-26. HTML: https://arxiv.org/html/2610.35631v1 ; DOI: https://doi.org/10.48550/arXiv.2610.35631 .
2. Authors' reproducibility repository, https://github.com/A2R-Lab/OSQPSlack , README and source at the current main revision inspected 2026-10-31. Git submodules pin A2R-Lab/osqp commit `2500405a1bc63387721feec64f0c050fa99223dd` and A2R-Lab/osqp-python commit `d6df7f987ba40e75bfac338ab19a97b2c92f7334`.
3. OSQP solver specification and settings: https://osqp.org/docs/solver/ and https://osqp.org/docs/interfaces/solver_settings.html ; C API and Python API docs at https://osqp.org/docs/interfaces/C.html and https://osqp.org/docs/interfaces/python.html .
4. Lew, Greiff, Subosits, Plancher, *Solving Quadratic Programs with Slack Variables via ADMM without Increasing the Problem Size*, arXiv:2511.08451, https://arxiv.org/abs/2511.08451 ; journal publication DOI 10.1016/j.ejcon.2026.101557.
5. Morton, Arrizabalaga, Manchester, Pavone, *ElastiQP: An Always-Feasible QP Solver for Constrained Robot Control*, arXiv:2609.19080, https://arxiv.org/abs/2609.19080 ; implementation https://github.com/StanfordASL/elastiqp .
6. DAQP soft-constraint formulation and implementation documentation: https://darnstrom.github.io/daqp/start/advanced/soft and https://github.com/darnstrom/daqp .
7. OSQP benchmark suite and its documentation: https://github.com/osqp/osqp_benchmarks . Current robotics MPC comparison dataset and protocol: https://qpsolvers.github.io/qpbenchmark/mpc_qpbenchmark/ ; source https://github.com/qpsolvers/qpbenchmark .
8. PIQP paper: https://arxiv.org/abs/2304.00290 . ProxQP paper and project page: https://scaron.info/publications/tro-2025.html . DAQP repository: https://github.com/darnstrom/daqp .
9. Official MPC soft-constraint formulation reference: MathWorks, *QP Optimization Problem for Linear MPC*, https://www.mathworks.com/help/mpc/ug/optimization-problem.html .
10. *ElastiQP* full arXiv HTML (formulation, comparisons and benchmark protocol): https://arxiv.org/html/2609.19080v1 .
11. *PIQP* full arXiv HTML: https://arxiv.org/html/2304.00290 .
12. Oshin, Ghosh, Saravanos, Theodorou, *Deep FlexQP: Accelerated Nonlinear Programming via Deep Unfolding*, ICLR 2026 proceedings and official paper: https://proceedings.iclr.cc/paper_files/paper/2026/hash/84cd19dedba8b8b7461d86c246f2c372-Abstract-Conference.html and https://openreview.net/pdf?id=HL3TvE4Afm . The proceedings page was inspected on 2026-10-31; it links the paper and does not list a code repository.

## Mathematical baseline

The hard QP is `min_x 1/2 x'Qx + q'x` subject to `l <= Ax <= u`, with symmetric positive-semidefinite Q. A common elastic formulation introduces a signed slack `xi` and minimizes `1/2 x'Qx + q'x + Phi(xi)` subject to `l <= Ax + xi <= u`.

The 2026 paper proves, for proper, closed, convex, unconditional `Phi` with `Phi(0)=0`, that the relaxed indicator is `g(z)=Phi(R(z))`, where `R(z)=z-Proj_[l,u](z)`. Its generalized projection is `Proj_[l,u](v) + prox_(Phi/rho)(R(v))`. This replaces the hard box projection in the OSQP ADMM update while retaining the same KKT matrix and factorization. The unconditionality condition means invariance under coordinatewise sign changes. The paper includes quadratic, l1, elastic-net, Huber, l-infinity, and l2 penalties, including grouped norms. It does not claim that all possible convex penalties are supported.

## Existing methods and product boundary

### Classical formulation

Explicitly lift slack variables and encode the penalty with variables/constraints, then solve with a conventional QP solver. This is the baseline and remains an essential correctness comparator. The number and structure of added variables depend on the penalty. For an l2 norm, a plain QP encoding is unavailable without conic treatment; OSQP is a QP solver, so conic comparisons must be separated.

### Recent OSQP soft-slack methods

The 2025 paper established the quadratic-penalty special case without adding slack variables. The 2026 paper generalizes the projection to unconditional convex penalties. The authors' OSQPSlack repository includes a modified C OSQP, matching Python bindings, per-row soft/hard masks and weights, grouped l2/l-infinity cases, explicit lifting helpers, random sparse QPs, building-energy MPC, committed result data and scripts, and a tutorial notebook. It is a reproducibility implementation of the paper, not a CAOS product template. Its reported benchmark compares native and lifted formulations on 100 generated instances at sizes 25 to 800 and reports up to 3.4x speedup on an M5 Pro; it does not establish universal superiority. Authors explicitly leave the difference in splitting and conditioning/iteration counts for future work.

### Current solver alternatives

ElastiQP is a distinct dual active-set implementation focused on dense robot-control QPs, with hard equalities and exact per-inequality l1 penalties; its public C++ library has Python/JAX interfaces. Its full paper evaluates feasible and deliberately infeasible robotics control loops and Maros-Meszaros problems. It distinguishes this from the OSQP Slack paper's broader convex penalty family and from lifted general-purpose soft QPs. DAQP documents and implements side-specific lower and upper linear/quadratic penalties in a dual active-set solver: each side has independent linear weight `w` and reciprocal quadratic weight `rho`. This directly defeats any claim that asymmetric soft costs themselves are new. PIQP is a proximal interior-point method intended for generic sparse QPs and robust ill-conditioned cases, making it a useful alternative solver, though its paper's standard slack variables are not the same semantic soft-penalty comparison. OSQP provides adaptive rho, vector rho, warm starts, matrix factorization reuse, infeasibility certificates and polishing; these existing capabilities must be retained in fair comparisons. General QP competitors used in modern MPC comparisons include DAQP, OSQP, QPALM, ProxQP, PIQP, Clarabel, HiGHS, Gurobi, MOSEK and others. Availability of solver packages does not imply equivalent soft-QP formulations or termination conditions.

### FlexQP and Deep FlexQP (new primary-source baseline)

The ICLR 2026 paper describes FlexQP as an always-feasible convex QP solver based on an exact `l1` elastic relaxation: feasible original QPs retain the original optimum, while infeasible cases minimize violation with sparse violated constraints. It uses an operator splitting inspired by OSQP, proves convergence under stated coercivity assumptions, and adds a learned LSTM parameter-feedback variant (Deep FlexQP). The published paper reports strong benchmark and nonlinear trajectory-optimization results; those numbers are paper claims and must not be repeated as CAOS measurements. The official proceedings abstract and OpenReview PDF were inspected. The proceedings entry does not expose an implementation link, and targeted exact-title GitHub searches found no official repository in this pass. Reproducibility is therefore open; reconstructing only FlexQP from the paper may be possible, but Deep FlexQP would require model/training data and a fair comparison budget. The product must list this as a documented availability limitation unless an author implementation is located.

FlexQP overlaps the product's intended infeasibility behavior and means the case contract must distinguish (a) user-defined soft penalties with fixed semantics from (b) exact feasibility restoration/violation minimization, which may choose a different objective. Comparisons should include FlexQP as a separate restoration baseline and must not imply semantic equivalence to every elastic objective. The learned Deep FlexQP performance claims motivate an explicit related-work discussion, not a numerical claim or silently reconstructed neural baseline.

## Candidate contribution to test

**Proposed method AAGSP: asymmetric, side-specific generalized slack projections in OSQP ADMM.** For each soft row, let violation residual `r_i = (Ax-u)_+ - (l-Ax)_+`, and define a signed separable convex penalty `Phi(xi)=sum_i phi_i(xi_i)` whose minimum is at zero but whose positive and negative sides can have different slopes/curvatures. A candidate update uses a side-specific proximal map on the signed projection residual, so overshooting an upper bound and undershooting a lower bound can have different costs without adding slack decision variables or changing the main KKT matrix.

#### Derivation sketch and conditions

For one interval `C=[l,u]`, define `g(z)=inf{phi(xi): z+xi in C}`. If `z` is inside C, zero slack attains the minimum. If `z>u`, feasible slacks lie at or below `u-z<0`, and convexity plus a minimum at zero makes `phi` nonincreasing as its argument moves toward zero on the negative ray; the minimizer is therefore `xi=u-z`. If `z<l`, the symmetric ray argument gives `xi=l-z`. Hence `g(z)=phi(Pi_C(z)-z)=phi(-R_C(z))` with `R_C(z)=z-Pi_C(z)`. The function is zero on C, uses `phi(l-z)` below the interval and `phi(u-z)` above it. Each branch is convex as an affine composition; the one-sided slopes join to zero with nondecreasing derivative, so g is closed convex. The argument extends coordinatewise to separable penalties and Cartesian interval sets; it does not cover coupled group penalties or non-interval feasible sets.

The split QP `min f(x)+g(z), Ax=z` is thus a two-block convex problem. Under the usual existence of a saddle point/solution and the base ADMM assumptions, standard two-block ADMM convergence applies; this does not itself prove OSQP's implementation details, adaptive-rho behavior, or infeasible/unbounded cases. For a scalar penalty with side slopes/curvatures `(a_+,a_-,b_+,b_-)`, the reflected prox `prox_{phi(-.)/rho}(r)` has positive branch `max((rho*r-a_-)/(rho+b_-),0)` for `r>0`, and negative branch `-max((rho*abs(r)-a_+)/(rho+b_+),0)` for `r<0`. Upper residuals correspond to negative original slack and thus use minus-side coefficients. Every sign is checked against an independent scalar convex minimization oracle before implementation.

This fills the algebraic derivation outline only. A formal proof with all domains, extended-real endpoints, equality rows, fixed rows, OSQP scaling, and convergence conditions remains required before source code.

Why it is promising: side-specific soft-constraint costs are already a meaningful control concept, as shown by DAQP. The 2026 OSQP paper's unconditional penalty assumption excludes these asymmetric penalties. An OSQP-native ADMM extension could combine that application feature with the paper's fixed-size KKT system and warm-start workflow.

Important novelty caveat: asymmetry itself is not new; DAQP already supports lower/upper-specific linear and quadratic weights. The potential contribution is a generalized slack-projection derivation and implementation in an OSQP-style ADMM method for a clearly defined asymmetric separable convex penalty family, and an apples-to-apples study against DAQP and explicit lifting. The literature search to date did not find a primary source proving that no such ADMM method exists. Until a fuller search and a correct proof are completed, describe this as a candidate extension and do not say “first” or “beyond state of the art.”

### Necessary derivation and falsification checks before accepting AAGSP

1. Prove the slack elimination identity for the exact asymmetric penalty family and interval constraints. Establish when signed scalar proximal solutions remain between zero and the input residual. Do not extend this result to coupled/asymmetric penalties without proof.
2. Prove the resulting reduced objective is closed convex and that the two-block ADMM convergence argument still applies under the stated assumptions.
3. Compare native asymmetric ADMM with explicit lifting in the same implementation/linear algebra backend, and against DAQP's native side-specific soft constraints. Include hard OSQP on feasible cases as a no-slack control.
4. Match objective and semantics first, then report setup, factorization, solve and total time; iterations; primal/dual/KKT residuals; objective gap against a high-accuracy reference; side-specific slack; and timeouts/failures. Do not rank tools from unlike default tolerances.
5. Use both controlled generated cases and application cases. A useful motivating case is building energy management where upper import exceedance and lower comfort undershoot need different consequences; test that setup against the paper's public building model and declare any changed assumptions. Add a small control/MPC family with disturbance sequences, held-out seeds and explicit hard/equality-row policies.
6. Use paired seeded runs, deterministic instance manifests, environment/CPU metadata, repeated timings, and uncertainty summaries. Preserve raw results and script hashes. Report negative and inconclusive results.

## Application and evaluation context

The paper's building example is a two-zone, battery, grid, 96-step one-day energy-management MPC and already demonstrates mixed penalty behavior. It is a useful baseline, but a product should not claim that recreating it is novel. Asymmetric penalties could encode unequal costs of discomfort below a band versus overheating above it, or import-limit exceedance versus reserve shortfall, provided units and scenario data are explicit. Control applications also use different hard/soft status by constraint: actuator/dynamics constraints often stay hard while selected state constraints soften. Any app must expose this distinction and not suggest that feasibility alone certifies safety.

The OSQP benchmark repository supplies broad QP families, but not necessarily soft-QP ground truth. The current qpbenchmark MPC set compares many solvers on a specific versioned robotics collection and records success, runtime and residuals. It is a useful protocol reference rather than a drop-in soft-slack benchmark. Public benchmark datasets, licences and exact transformations must be audited before inclusion; no raw third-party dataset should be assumed redistributable.

## Implementation review of OSQPSlack

Reviewed the authors' public README, repository outline, Python penalty adapters, random QP generator, energy model, benchmark runner, C solver headers and penalty implementation. The solver is a modified upstream OSQP C codebase with codegen support and matching modified Python bindings, not a Python-only wrapper. Penalty setup occurs after ordinary OSQP setup; penalty parameters can be updated and slacks recovered; non-separable norm penalties use group IDs; scale transformations and dual feasibility are handled in the C core. The repository also supplies explicit lifting and checks native/lifted objective consistency. This is the real implementation baseline. Any new product should consume or vendor through a clearly versioned upstream-compatible fork, with exact license/notice preservation and a pinned commit, rather than reimplementing only the projection formula in a toy Python loop.

Submodule pins were confirmed at OSQP `2500405a1bc63387721feec64f0c050fa99223dd` and osqp-python `d6df7f987ba40e75bfac338ab19a97b2c92f7334`. Both nested projects carry Apache-2.0 license text; OSQPSlack's top-level `LICENSE` is MIT. Its Python and CMake build configuration is present. This establishes a plausible redistributable source route, not a validated wheel/build or complete third-party notice inventory. Package creation still depends on a full notice/license audit, upstream diff review, platform build matrix and independent solver tests.

## Source-specific limits

- arXiv:2610.35631 is version 1 and was submitted five days before this dossier date. Its results are paper-specific, machine-specific and compare its implementation against explicit lifting, not every current solver.
- OSQPSlack's repository data and claims reflect the paper authors' configuration; timings are not transferable to the CAOS device. Re-run before using any values.
- ElastiQP's abstract claims and repository description motivate comparison, but any quantitative claims require checking the full paper's exact protocol and reproducing compatible cases.
- DAQP's documentation confirms side-specific soft weights, so asymmetry is not a novel problem formulation by itself.
- FlexQP already supplies an exact `l1` elastic feasibility-restoration method and Deep FlexQP a learned acceleration for QPs; AAGSP's potential distinction is the family of user-selected convex penalty functions and asymmetric interval-side costs inside generalized OSQP projection, not always-feasible behavior or `l1` exactness. The non-equivalence and comparison boundary still need formal SDD treatment.
- Search absence is not proof of novelty. The AAGSP candidate is not yet a proven theorem, implementation, validated speedup, or accepted beyond-SOTA method.
