# SoftQP Studio

[![CI](https://img.shields.io/github/actions/workflow/status/fsantibanezleal/CAOS_SoftQP/ci.yml?branch=main&label=CI)](https://github.com/fsantibanezleal/CAOS_SoftQP/actions)
[![License](https://img.shields.io/github/license/fsantibanezleal/CAOS_SoftQP)](LICENSE)
[![Version](https://img.shields.io/github/v/tag/fsantibanezleal/CAOS_SoftQP?label=version&sort=semver)](https://github.com/fsantibanezleal/CAOS_SoftQP/tags)
**The [research-preview releases](https://github.com/fsantibanezleal/CAOS_SoftQP/releases) are available at the [verified public workbench](https://fsantibanezleal.github.io/CAOS_SoftQP/).** Both registered timing-improvement criteria remain unsuccessful; deployment establishes availability, not scientific qualification or operational benefit. The served build identifies its exact version and commit in `build.json`.

[Software archive, latest version](https://doi.org/10.5281/zenodo.23891595) · [native LaTeX sources](manuscripts/README.md)

Explore seven soft-constraint QP methods and the evidence from two timing studies.

*Explora siete métodos para QP con restricciones blandas y la evidencia de dos estudios de tiempos.*

## Areas

The repository by area: its folder, whether the area is active or dormant, and what it holds.

| Area | Folder | Status | What it holds |
|---|---|---|---|
| Web | [`frontend/`](frontend/) | active | The workbench and the documentation routes on the shared shell. Build and test: `cd frontend && npm ci && npm run build && npm test`. |
| API | [`app/`](app/) | dormant: this solution does not require it at the moment | Ships dormant; activation is [guide 04](docs/guides/04_run-the-api.md). |
| Core pipelines | [`data-pipeline/`](data-pipeline/) | active | The named pipeline stages and the bake: `./scripts/precompute.sh all --output OUTPUT`. See [data-pipeline/README.md](data-pipeline/README.md). |
| Packages | (PyPI) [softqp 0.1.0](https://pypi.org/project/softqp/0.1.0/) and [0.2.0](https://pypi.org/project/softqp/0.2.0/) | active: separate pinned ordinary and advanced-teaching profiles | The separate [native engine](https://github.com/fsantibanezleal/CAOS_SoftQP_Engine) owns the implementation. The app uses SDK1; the [advanced lesson](notebooks/en/01-soft-constraint-decisions/05-directional-group-peaks.ipynb) explicitly isolates SDK2. Public-index distribution and installation are verified. |
| Notebooks | [`notebooks/`](notebooks/) | active | The didactic notebooks in English and Spanish, by topic and level. Run: `./scripts/setup.sh --notebooks`, then `python scripts/run_notebooks.py`. Guide: [guide 08](docs/guides/08_notebooks.md). |
| Data | [`data/`](data/) | active | The committed derived artifacts and the sources with their licence classes. |
| Contracts | [`docs/contracts/`](docs/contracts/) | active | The contract catalog and the schemas. |
| Documentation | [`docs/`](docs/) | active | The SDD ([docs/design/SDD.md](docs/design/SDD.md)), the [guides](docs/guides.md) and the case pages. |
| Tests and gates | [`tests/`](tests/), [`scripts/`](scripts/) | active | `python -m pytest` and the checks (`scripts/check_*.py`). See [scripts/README.md](scripts/README.md). |
| Deploy | [`deploy/`](deploy/) | active: verified GitHub Pages research preview | Where it is deployed and how, never credentials. |

See [the scientific development workflow](docs/softqp-development.md) for the actual fifteen-case bake and local cost editing, native execution and verified import. The native scientific core and paired experiment exports are implemented. The research-preview release passed its engineering and distribution checks; both unsuccessful scientific criteria remain unchanged.

## Run it

Configure absolute external CAOS_VENVS_ROOT and CAOS_TEMP_ROOT before initialization. Raw data and models, when
needed, use CAOS_DATA_ROOT and CAOS_MODELS_ROOT. The [local workflow](scripts/local/README.md) documents both shells,
exact runtime names, readiness exceptions and source-bound promotion.

```bash
bash scripts/local/00_install-prereqs.sh
bash scripts/local/01_init.sh
bash scripts/local/03_dev.sh
```

PowerShell uses the matching .ps1 entrypoints. Opening complete shipped data does not execute either registered study.
Explicit `02_generate-data` creates a fresh external authored-case stage; only `--release --from-stage <stage>`
(or `-Release -FromStage`) promotes its validated compact artifacts. Historical campaign inputs remain byte-bound.
The current runtime is created at CAOS_VENVS_ROOT/softqp/.venv-local. Optional teaching/API runtimes are separate;
the three historical scientific/notebook environments are preserved.

The frontend checks run with `cd frontend && npm run build && npm test`. Run the full measured browser gate with
an explicit external output directory. Teaching instructions and unchanged historical SDK pins are in
[notebooks](notebooks/README.md); the separately pinned coupled SDK/reproduction instructions are in the
[coupled study](manuscripts/coupled-peak-study/reproduction.md).

## Documentation

- [docs/design/SDD.md](docs/design/SDD.md): the design, every requirement with its gate.
- [docs/](docs/README.md): architecture, guides, cases and frameworks.

Licensed under the MIT License (see [LICENSE](LICENSE)), with the separate explanatory-material terms in [LICENSES.md](LICENSES.md). Pages deployment passed exact-main CI, route/404/build checks, anonymous verification of all 39 declared data files and actual deployed-browser interaction with independent review.

## Measured finding

The frozen 456-instance experiment retained 11592 accepted measured observations and 7560 explicit incompatibilities, without numerical failures or accuracy rejection. The primary timing hypothesis did not pass: median relative reduction 0.50%, 95% seed-cluster interval -3.29% to 3.94%, below the registered 10% criterion. This negative result is preserved in the raw evidence and curriculum; it establishes no timing superiority or global algorithmic novelty.

The [technical report](https://doi.org/10.5281/zenodo.23851659) documents the formulation, methods, complete experiment and limits under CC BY 4.0.

The separate 210-instance directional group-peak study retains its negative result: the median paired reduction
score is -212.449875%, with 95% limits [-225.336618%,-192.873759%] and nine prescribed failed pairs.
[The separate research preprint](https://doi.org/10.5281/zenodo.23875071) and the
[complete archived evidence](https://doi.org/10.5281/zenodo.23875194) document all outcomes and exact assumptions.
The [product technical report](https://doi.org/10.5281/zenodo.23851659) covers methods, contracts and product scope.
The research preprint derives both original-row updates and presents their distinct experiments.
Both use the canonical section-based LaTeX article template; [editable sources and build instructions](manuscripts/README.md)
are available alongside the PDFs. Neither registered improvement criterion is established.
The current independently verified replacements are [technical report 0.01.003](https://doi.org/10.5281/zenodo.24122924)
and [research preprint 0.02.003](https://doi.org/10.5281/zenodo.24122893).

The complete numerical validation uses [explicit test profiles](docs/testing-profiles.md): the ordinary public-wheel regression, exact historical-source positive controls and the separate SDK2 suite. Source identity is never replaced by a matching version label.

The current 0.01.003 candidate includes a fresh, externally staged bake of all fifteen authored cases and manifests.
The workflow validated original-space metrics, contracts, document inventories and current-version readiness before
promoting the stage. The six historical registered-experiment inputs were carried byte-for-byte; neither timing
study was rerun or altered by this case bake. The committed case results are newly computed and have their own
execution timings, which are descriptive rather than substitutes for the frozen studies.
