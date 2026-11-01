# Measured resources and experimental outcome

The protocol was registered on 2026-10-31 before held-out generation. The completed run used app runner source `1a0c664` and engine `d0c69ed974d577ba02adbd4806332270d9425651`. The authoritative evidence is the [campaign manifest](../../data/derived/experiments/campaign.json), [artifact inventory](../../data/derived/experiments/index.json) and complete raw trial files. The experiment is a local computational study, not release acceptance.

## Observed campaign resources

| Quantity | Observed value | Scope |
|---|---|---|
| Completed instances | 456 | 144 development, 288 held-out, 24 robustness |
| Wall time | 1363.063 s | Entire generation/oracle/worker/export campaign |
| Worker peak RSS | 92028928 bytes (87.766 MiB) | OS-observed worker high-water, not isolated method allocations |
| Worker restarts | 0 | Timeout/resource recovery events |
| Accepted measured observations | 11592 | Warm-ups excluded |
| Incompatible measured cells | 7560 | Retained with reasons |
| Experimental artifact bytes | 22356819 | JSON, JSONL, CSV, and the C12 stream; inventory itself excluded |
| Current derived tree bytes | 24671035 | All 41 files, before a final release rebake |

The worker budget was one process, one BLAS/OMP/MKL thread, a 10 s trial deadline, 7200 s campaign limit and 4 GiB RSS polling limit. These observed values do not establish a native allocation bound, a GPU requirement or a browser-live execution budget.

## Primary registered result

The median paired relative cold end-to-end reduction was 0.499839%, 95% seed-cluster interval [-3.291967%, 3.944835%], over 168 accepted pairs and six held-out seeds. No compared pair was rejected. The registered target of at least 10% with a positive lower interval endpoint was **not established**. No subset replaces that result.

All 11592 accepted measured observations satisfy the registered original objective and hard-row limits. There were 7560 explicit incompatibilities and no numerical, timeout or accuracy-rejected measured observations. Compatibility is a property of the declared family and adapter, not a failed scientific evaluation silently removed from a denominator.

## Control stream

C12 has 32 common-oracle state inputs with impulses at frames 8 and 20. Three compatible methods each have cold/warm observations at every frame: 192 accepted observations. Generalized symmetric projection contributes 64 incompatible cells because side prices differ. One observation per frame is descriptive, not a statistical timing result. Initial workspace setup is recorded separately.

## Distribution and UI boundaries

A clean Windows source install initially failed because MSBuild compiler-test paths exceeded 260 characters. Retrying with a short temporary root succeeded and produced a normal installed wheel. The engine release branch repairs the default build path and adds portable wheels built from the source archive, clean-wheel tests and license checks. Version 0.1.0 is now published on PyPI. All public files match tagged workflow 41323753954; a fresh public-index Windows install passes 94 native tests and license checks. The original timing environment remains unchanged.

The earlier focused shared-shell gate passed 171 states at 1280x800 and 390x844 in light/English before the campaign/stream view additions. It is historical focused evidence, not the current full five-size/two-theme/two-language release gate. Static replay remains the declared lane; no browser-native solver budget or parity pass is claimed.

## Reproduction

Install the exact historical engine source in the protocol for the frozen experiment. Package version alone is insufficient to identify its numerical binary. Run the experiment CLI into a fresh explicit output directory; preserve all raw states and use `publish --campaign-input SOURCE --output DESTINATION` to validate and export. New packaging metadata or a different machine must not be presented as the original timing environment.

## Static reader resource observations

Build `55a7e77415f2f73334ffbce286d3559f8a81152a` contains 153 static files totaling 34336119 bytes. The [raw resource observations](static-reader-resources.json) retain the browser version, exact build identity, resource body sizes, sampled V8 heap and DOM counts. The local static server did not apply production compression. Resource body totals are not a measurement of wire traffic, and sampled heap is not a peak-memory bound.

| Viewport | Route / case | Encoded resource body bytes | Sampled used heap bytes | DOM elements |
|---|---|---|---|---|
| 1280x800 | app/C01 | 1069419 | 15293152 | 243 |
| 1280x800 | app/C13 | 1496600 | 24543988 | 661 |
| 1280x800 | benchmark | 5832389 | 15342108 | 1565 |
| 390x844 | app/C01 | 1069419 | 15296376 | 243 |
| 390x844 | app/C13 | 1496600 | 24575640 | 652 |
| 390x844 | benchmark | 5832389 | 15281992 | 1565 |

Both sizes use desktop Chromium with emulated viewports. These are local observations of verified static replay, not physical-phone performance, a deployed origin, or browser-native solver execution. The configured static-hosting candidate still requires exact-commit deployment and served-artifact checks. The failed scientific improvement criterion remains a separate, binding release condition.
