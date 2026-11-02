# DAQP active-set reference

## What and why

DAQP already handles distinct lower/upper soft weights, so asymmetry is not a novel modeling capability. Its dual active-set algorithm is a necessary baseline alongside ordinary lifting.

## Install: exact declared version

`daqp==0.10.3`. Numerical source validation uses Python 3.12. See the repository requirements rather than substituting an ambient version. Native source installation additionally requires a C/C++ compiler and CMake; clean published-wheel installation has its own release check.

## Usage

The adapter maps positive quadratic b to reciprocal weight 1/b and passes linear side prices in original units. Global linear fallback is set to zero so an individual zero stays unpriced.

## Applying it here

Positive definite elastic cases join the comparison. DaqpWorkspace updates vectors without resending sense flags, preserving active state for a fair warm comparison.

## Caveats and license

MIT. This adapter refuses semidefinite curvature and pure L1 finite soft sides. It does not insert regularization or a tiny quadratic price. DAQP soft-optimal status two is interpreted using DAQP semantics.

Primary source: [DAQP active-set reference](https://darnstrom.github.io/daqp/start/advanced/soft).
