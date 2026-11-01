# ElastiQP L1 reference

## What and why

The published DAS backend supplies an independently implemented pure L1 comparator. It receives finite-side weighted inequalities and a separate hard-equality interface; it is not a proxy for every mixed soft-constraint objective.

## Install: exact declared version

`elastiqp==0.2.0`. Numerical source validation uses Python 3.12. See the repository requirements rather than substituting an ambient version. Native source installation additionally requires a C/C++ compiler and CMake; clean published-wheel installation has its own release check.

## Usage

Call `softqp.elasti.solve_elastiqp(problem, eps_abs=..., eps_rel=...)` on a compatible positive definite problem. The adapter recovers signed original row multipliers.

## Applying it here

Local pure L1 variants and the controlled L1 family compare it with independent lifting, asymmetric projection and the paper-equation FlexQP reconstruction.

## Caveats and license

Apache-2.0. Hard inequalities, quadratic soft costs and non-positive-definite P are refused. Actual settings are exported; the comparison uses zero objective regularization.

Primary source: [ElastiQP L1 reference](https://github.com/StanfordASL/elastiqp).
