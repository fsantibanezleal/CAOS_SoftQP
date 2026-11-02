# Local workflow

Run commands from any directory using the entrypoint's absolute path, or from the repository root as below.
The numbered steps share workflow.py and the declarative workflow.json. Flat setup/dev/precompute scripts remain compatible.

## 00: system prerequisites

PowerShell: ./scripts/local/00_install-prereqs.ps1

Bash: bash scripts/local/00_install-prereqs.sh

The default checks Python>=3.12, Node ^22.12.0 || ^24.0.0 || >=26.0.0 and git. Newer compatible installations are accepted.
Only -Install / --install requests installation of missing prerequisites, through winget on Windows or Homebrew
where available. Otherwise the command explains the manual repair. No global Python package is installed.
PYTHON can select an existing interpreter path, including one containing spaces.

## 01: initialize

PowerShell: ./scripts/local/01_init.ps1

Bash: bash scripts/local/01_init.sh

Initialization copies nonsecret .env.example defaults only if .env is absent. Existing .env bytes are preserved;
dotenv assignments are literal values, never shell commands. Exported process variables take precedence.
Declared ignored venvs and locked frontend dependencies are provisioned. Recursive requirements and package-lock
fingerprints are stamped only after a successful install; a matching installation is reused. A failed native
process is a failure, while successful native stderr warnings remain warnings.

Optional -Notebooks / --notebooks provisions the notebook environment. See the product notes below for the optional GPU lane.
Complete shipped artifacts avoid acquisition or generation. If required artifacts are genuinely absent, initialization
runs the complete external sandbox generation path and reports the explicit promotion command needed before dev.
It never silently replaces committed artifacts or starts a science bake as part of an ordinary complete checkout.

## 02: external data generation and explicit promotion

Configure CAOS_TEMP_ROOT as an external scratch root before generation. No system-temp or repository fallback is used.
PowerShell: ./scripts/local/02_generate-data.ps1

Bash: bash scripts/local/02_generate-data.sh

Each invocation creates a fresh external caos-local-* stage. All measured summaries, process records, exported models
and local checkpoints remain there. The complete real producer plan is in workflow.json; no stage inherits a
repository output default. Pinned source caches, when needed, use external CAOS_DATA_ROOT. This operation can be
expensive and may require source acquisition and generation dependencies; opening shipped artifacts does not.

After generation, the command prints the stage and next command. Promotion requires explicit intent:

PowerShell: ./scripts/local/02_generate-data.ps1 -Release -FromStage '<external stage>'

Bash: bash scripts/local/02_generate-data.sh --release --from-stage '<external stage>'

Without a supplied stage, explicit release mode first generates a fresh complete stage. It rechecks current source
and payload fingerprints, versions, whole catalog/readiness, and the existing semantic/schema validators before
replacement. Mixed, partial, changed or invalid candidates cannot replace old files. Prepared incoming trees and
backups support rollback if any artifact/model-directory promotion fails. Every recoverable target is attempted;
if restoration fails, the error names original and restoration failures and all retained recovery paths.
Preserve those paths until recovery is complete; never delete backups merely to silence an error. Checkpoints are never release payloads.
Here release means local artifact promotion; it creates no Git tag, software release, deployment or publication.

## 03: development services

PowerShell: ./scripts/local/03_dev.ps1

Bash: bash scripts/local/03_dev.sh

The helper verifies initialized dependencies, the frontend lock fingerprint, shipped artifacts and free loopback
ports. It runs the existing frontend predev copy, starts Vite directly, and supervises an active API where declared.
The API must answer health before the frontend starts. Child failure exits nonzero; Ctrl+C stops only this
workflow's process trees. It does not kill a pre-existing process or install dependencies during startup.

## Checks

Run the focused behavioral suite with the initialized pipeline interpreter:

python -m pytest tests/test_local_bootstrap.py tests/test_bootstrap_regressions.py -q

The fixtures execute fake producers and local HTTP/frontend subprocesses in external temporary repositories,
not training or release promotion in this checkout. Use the existing smoke scripts for the full product gates.
Actual installed app launch, API operations, release publication and deployment require their own observed receipts.

## SoftQP workflow contract

The default local environment is `.venv-local`; the optional API and lesson environments are
`.venv-api` and `.venv-lessons`. The historical `.venv-pipeline`, `.venv-notebooks` and registered
`.venv-coupled` environments are not initialized or changed by this workflow. Declare ignored
runtime-directory aliases pointing into an external environment root before initialization.

The API is explicitly dormant. The complete shipped fifteen-case artifacts are opened without a
scientific bake. Their readiness excludes its own row and reports the dormant API and three
undeployed coupled-study artifact exchanges as missing; these four explicit outcomes are checked
by the real readiness producer. Every other missing or partial row is refused.

The producer adapter solves the authored fifteen-case matrix only into an external stage. It
preserves the existing registered historical experiment files as byte-bound stage inputs and never
reruns, retimes or regenerates either registered scientific study. Source identity includes those
exact inputs. Validation requires all fifteen distinct cases, all four canonical matrix methods exactly once, consistent method-specific terminal statuses, valid result hashes, the complete
historical observation inventory and exact frozen input bytes. Local artifact promotion is a
separate explicit operation and does not qualify a software release or deployment.

The stage promotes `data/derived` only; this deterministic solver product declares no model slot.
A coupled-study browser replay adapter is not supplied by this workflow. Its archived evidence
remains an offline research artifact. New evidence cannot be admitted merely by placing JSON in
the app data root or by editing a readiness exception.

Set external `CAOS_TEMP_ROOT`, `CAOS_DATA_ROOT` and `CAOS_MODELS_ROOT` as applicable. The frontend
receives its own declared compact-tree override; generation/API/caller storage variables retain
their separate roles. No literal device path belongs in the repository.

## External runtimes

Set absolute CAOS_VENVS_ROOT before initialization. The namespace is softqp and the primary declared runtime
is .venv-local; optional API and teaching runtimes are .venv-api and .venv-lessons. They are created below
the external role root, never inside this checkout. The three historical scientific/notebook environments
are preserved separately and are not overwritten by initialization. Missing, internal, redirected and
non-directory runtime paths refuse before any installation or .env creation.
