# Design: case-dependent inspection from native artifact to screen

This is a current reconciliation of the implemented end-to-end workbench. The historical feature name referred to the template example; the active domain is the soft-QP case catalog. The design explains current producer/reader dependencies without asserting that this document existed before their implementation.

## A case is mathematical input, not a picture

`pipeline.softqp_cases.cases` enumerates the authored problem catalog with case IDs, bilingual names, source and original numerical inputs. `pipeline.softqp_run.run_case` produces the declared method states and original-space metrics. The ingestion and expectation boundaries refuse malformed or out-of-range inputs rather than filling a missing value from a different case. Deterministic case encoding is distinct from elapsed time: the same seed fixes the mathematical input, but separate wall-clock executions are not promised byte-identical durations.

`pipeline.core.manifest.export_manifests` links the scientific results to the deployable manifest/index and byte inventory. Each consumer therefore has a path, schema and digest authority. A same-size changed byte is still a changed result. The test-session artifact snapshot in `tests/conftest.py` prevents a passing test from quietly rewriting canonical results, including when its own assertions succeed.

## Loading, state and rendering

`frontend/src/lib/softqp.ts` loads the scientific index and selected result, verifies SHA-256 and case identity, and applies the result schema. `frontend/src/api/artifacts.ts` serves the shared manifest/readiness artifact path through `getJSON`; a response must be successful JSON rather than a static host's HTML fallback. These paths have distinct responsibilities, so the shared artifact transport is not misrepresented as the native solver.

`frontend/src/workbench/Workbench.tsx` composes the shell's `CaseWorkbench`. The chosen case, method and original row unit determine its data and its selection key. The selected unit scopes hard-row readouts; no hard row in that unit gives an unavailable KPI rather than an invented zero. `StreamStage` provides the C12 recorded stream when its case and method apply. Local cost edits use an exported request and verified native import, while the interface keeps the imported origin visible.

Changing a registered control updates the selection key observed by every view. A slow previous case load cannot become the current result after selection has changed. Input editing that changes the intended import identity also invalidates a pending previous import. Unsupported grouped edits are disabled/refused rather than being interpreted as separable penalties. Source/provider labels and readiness reasons remain visible beside usable content.

## Spatial and route constraints

The shared workbench supplies its rail, question groups, Context surface and Focus behavior. Product code supplies the numerical/domain content, not another shell frame. Static route materialization preserves direct links with and without a trailing slash, and the browser gate measures the actual built product rather than a different service already listening on a port.

The inherited EX-010 requirement and its G6 check state the older half-viewport floor. They are not claimed as acceptance of the current stronger stage/story visualization obligations. Those need the active catalog, linked views, narrow/wide interaction checks and independent capture reading. The same distinction holds for G9 selection-key wiring: a source attribute is not proof that every visible result actually changed with the selected case.

## Proof obligations and alternatives

EX-001/EX-004 map expectations and malformed input to their actual Python tests. EX-002 checks deterministic input encoding and changed-byte refusal. EX-003 binds test behavior to the canonical artifact snapshot. EX-005/EX-008 bind actual JSON producer/consumer keys and transport rejection. EX-009 covers direct-route output, EX-010/EX-011 measured spatial/state behavior, and EX-012 version coherence.

An equal-chart grid with disconnected controls was rejected as the primary analytical view; meaningful domain content and shared selection are required. Ignoring HTML response types was rejected because it hides a missing artifact behind an unrelated parse failure. Using a small digest as proof of mathematical correctness was rejected because numerical admission has separate original-space checks. [Validation](validation.md) retains those counterexamples and [tasks](tasks.md) orders the producer, transport, state and measured acceptance dependencies. No deployment, physical safety or speed-superiority verdict follows merely from compiling this composition.
