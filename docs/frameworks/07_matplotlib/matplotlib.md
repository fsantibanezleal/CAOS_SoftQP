# Matplotlib lesson figures

## What and why

The executable curriculum needs standalone figures with physical axes, explicit units and written interpretations. Matplotlib provides deterministic static plots under the pinned execution environment.

## Install: exact declared version

`matplotlib==3.11.2`. Numerical source validation uses Python 3.12. See the repository requirements rather than substituting an ambient version. Native source installation additionally requires a C/C++ compiler and CMake; clean published-wheel installation has its own release check.

## Usage

Each notebook creates its own labeled figure and the fresh-kernel runner preserves executed PNG output. A subsequent markdown cell interprets what the plot establishes.

## Applying it here

Used for scalar objective curves, physical state/actuator predictions, matched representation counts and the registered effect interval.

## Caveats and license

Matplotlib license based on the PSF license. Figures are not copied paper plots; output-byte reproducibility is checked on the environment that produced the committed notebooks.

Primary source: [Matplotlib lesson figures](https://matplotlib.org/stable/).
