# Native soft-QP engine

## What and why

The separate distribution contains the pinned C/pybind solver, original-space problem API, compact/side-specific lifts, reusable workspaces and bounded DAQP/FlexQP/ElastiQP adapters. It is chosen because a browser-only demonstration cannot exercise the authors' native penalty code, scaling or recession checks.

## Install: exact declared version

`softqp==0.1.0`. Numerical source validation uses Python 3.12. See the repository requirements rather than substituting an ambient version. Native source installation additionally requires a C/C++ compiler and CMake; clean published-wheel installation has its own release check.

## Usage

Construct `softqp.problem.Problem` and call `softqp.solvers.solve(problem, method="asymmetric")`. Repeated fixed-matrix vectors use `PreparedSolver`; DAQP has its own retained-state workspace.

## Applying it here

The app consumes an exact declared distribution version; its historical experiment separately records source d0c69ed974d577ba02adbd4806332270d9425651. [Version 0.1.0 is published on PyPI](https://pypi.org/project/softqp/0.1.0/). Its public source archive and both portable wheels match the tagged publishing workflow; a fresh public-index Windows install passes all 94 native tests and license checks.

## Caveats and license

Apache-2.0 AND MIT AND BSD-3-Clause. OSQP/bindings, reference helpers and AMD notices are retained separately. The CPU builtin backend is supported. Mutable penalty type/weight updates are not exposed.

Primary source: [Native soft-QP engine](https://github.com/fsantibanezleal/CAOS_SoftQP_Engine).
