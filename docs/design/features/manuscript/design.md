# Design: separate native technical report and research paper

This is a retrospective description of the current authoring, compilation and publication boundaries. The two editable documents already exist; this design does not manufacture a pre-implementation review history. Their purposes differ: the technical report explains all product methods, data contracts and computational scope, while the research preprint derives the two related updates and reports their distinct negative timing studies.

## Sources, base and document identity

`manuscripts/soft-constraint-study/main.tex` and `manuscripts/coupled-peak-study/main.tex` are separate native article sources. Their local base and included section files carry section-numbered mathematics, algorithms, bibliography and vector figures. The report identifies itself as Technical report and the research article as Preprint; the paper has no chapter commands. Front matter declares document type, version, version DOI and concept DOI, with sole-author ORCID and programme affiliation. The boxed identity follows the title and precedes the abstract.

Each folder's `coverage.json` links the document's title to actual tables/figures and maps the relevant methods or claims. The report additionally maps every contract. The measurement driver `scripts/manuscript_content_bar.py` reads the source rather than trusting a `product.json` declaration. Word, equation, figure, table, cited-reference and algorithm floors complement the required sections and per-method coverage. A count cannot replace a reader checking that the equations are used, every float is interpreted and each claim follows from the evidence.

## Evidence-derived assets

`manuscripts/shared/generate_assets.py` generates the literal tables and vector figures for both documents from the separately identified frozen authorities and records their input and figure inventories. Each document's `build.py` verifies or explicitly refreshes its numerical macros and then delegates native compilation to `scripts/build_manuscript.py`; it does not generate those tables or figures. The original separable study and subsequent directional study retain different source identities, populations and endpoints. The shared compiler's `require_evidence` verifies the immutable original stream and the accepted coupled summary before compiling; replacing an unfavorable estimate, changing a denominator or supplying a rehashed altered authority remains a refusal.

Input provenance matters even when the PDF looks correct. The compiler inventories recursively included TeX, bibliography and figure inputs, rejects missing or escaping paths, and compares identities before and after the build. Policy and compiler identities are recorded separately from document inputs. Figures remain native vector PDFs and equations remain LaTeX mathematics; rasterized equations or text drawn through a graphics PDF generator are not an alternate manuscript path.

## Compilation and publication admission

`scripts/build_manuscript.py` invokes pdflatex and the bibliography workflow, resolves cross-references through repeated passes and produces a build receipt beside the output. Unresolved citations/references or clipped typesetting fail. The receipt binds PDF digest, recursive input inventory, policy inventory and compiler driver. Compilation takes place under an explicitly supplied external output root; authored sources remain editable in the repository.

`scripts/publication_acceptance.py::require_acceptance` consumes the actual source, PDF, build receipt and independently issued review. The caller supplies an external trusted digest of that review; a candidate-controlled digest cannot authorize itself. The review must bind title, resource type, version identifiers, complete source/PDF identities and explicit content, mathematics and all-page acceptance. Before-reservation and before-publication are different phases. The final phase requires the actual reserved version identifier in the reviewed PDF rather than only its stable concept identifier.

## Failure, alternatives and verification

An absent source or unsupported document identity is refused before publication. Supporting numerical evidence belongs to a separate related dataset, while each manuscript record contains exactly its manuscript PDF. A copied past review does not accept changed source, and an uploaded checksum alone does not establish the complete public file inventory. Successful publication does not turn either negative timing result positive.

A single merged report was rejected because product documentation and research claims require distinct scope and metadata. A minimal decorative article was rejected because every implemented method, contract and result needs substantive coverage. The current architecture is checked by MS-001 through MS-004 for native structure/identity, MS-005 for immutable evidence, MS-006/MS-009 for compilation and input binding, MS-007/MS-008 for full content and MS-010 for independent publication admission. `tests/test_manuscript_sources.py` contains the named hostile cases. [Tasks](tasks.md) orders these dependencies; [validation](validation.md) retains the exact counterexamples. Fresh page inspection and actual public-record verification remain separate acceptance obligations.
