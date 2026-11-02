# NumPy

## What and why

NumPy provides original variable arrays, side masks and independent arithmetic for objective recomputation. Vector operations retain original row order; a lift does not rename or aggregate physical violations.

## Install: exact declared version

`numpy==2.5.4`. Numerical source validation uses Python 3.12. See the repository requirements rather than substituting an ambient version. Native source installation additionally requires a C/C++ compiler and CMake; clean published-wheel installation has its own release check.

## Usage

The evaluator computes `0.5*x@(P@x)+q@x` and separately prices positive lower/upper departures. Boolean inputs cannot stand in for numeric coefficients.

## Applying it here

Used throughout authored generators, adapters and independent acceptance. Array shape and dtype checks precede native calls.

## Caveats and license

BSD-3-Clause. Floating-point reductions and stopping tolerances do not imply exact arithmetic; seed control does not make wall-clock times deterministic.

Primary source: [NumPy](https://numpy.org/doc/stable/).
