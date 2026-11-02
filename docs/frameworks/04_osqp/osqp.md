# Independent stock OSQP

## What and why

Stock OSQP solves an ordinary lifted QP independently from the modified native fork. Keeping an independent implementation helps detect incorrect objective, projection or dual-recovery logic. The timed lift instead uses the matching native fork to avoid conflating backend builds.

## Install: exact declared version

`osqp==1.1.3`. Numerical source validation uses Python 3.12. See the repository requirements rather than substituting an ambient version. Native source installation additionally requires a C/C++ compiler and CMake; clean published-wheel installation has its own release check.

## Usage

Call `solve(problem, "lifted", reference_backend="stock")`. Use the native reference backend only where a matched timing protocol calls for it.

## Applying it here

High-accuracy oracle settings use absolute and relative tolerances 1e-9 in the campaign. Original hard error and objective are recomputed outside the solver.

## Caveats and license

Apache-2.0. Status two denotes an inaccurate solution and is not silently equated with solved. Generalized side penalties belong to the pinned fork rather than stock OSQP.

Primary source: [Independent stock OSQP](https://osqp.org/docs/solver/).
