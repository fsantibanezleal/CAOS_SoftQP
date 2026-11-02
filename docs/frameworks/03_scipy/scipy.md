# SciPy sparse and linear algebra

## What and why

SciPy supplies CSC matrices, sparse convexity checks, dense reference factors and the preserved building discretization. It is retained rather than introducing a second hand-written sparse format or an unverified linear algebra substitute.

## Install: exact declared version

`scipy==1.18.1`. Numerical source validation uses Python 3.12. See the repository requirements rather than substituting an ambient version. Native source installation additionally requires a C/C++ compiler and CMake; clean published-wheel installation has its own release check.

## Usage

Public P is fully symmetric. The adapter extracts its upper triangle only at a backend seam. Sparse decoding validates column offsets and sorted unique row indices.

## Applying it here

The pipeline builds coupled controls and the building model with sparse matrices. FlexQP uses a dense Schur Cholesky inside its bounded reference budget.

## Caveats and license

BSD-3-Clause. Sparse validation and dense conversion costs belong to the measured implementation. No isolated factorization time is inferred from unrelated timers.

Primary source: [SciPy sparse and linear algebra](https://docs.scipy.org/doc/scipy/).
