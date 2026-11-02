# Static deployment and source promotion

GitHub Pages is the configured host for the static reader. The native engine does not run on Pages. Vite materializes six routes plus a fallback document and a build identity. The copy stage ships exactly the deployment inventory's declared files, including experimental raw downloads, and stops when a required declared artifact is absent.

The scientific inventory and deployment wrappers are separate contracts. A wrapper records native package version, product version, case source, seed, artifact path/size/digest and the replay-lane reason. The deployment index's compatibility field `engine_version` tracks the product pipeline version; it is not the Python distribution version. Confusing these fields would make legitimate version checks meaningless.

Source promotion follows task branch to develop to main. Each promotion requires exact-head CI; green checks from a parent commit are not substitutes. Release acceptance then verifies the served build identity, every materialized route, artifacts and SHA-256 inventory, phone/desktop behavior, both languages/themes and authorization boundaries of any activated API. A local static build and a focused screenshot remain scoped evidence.

The native distribution has its own build, license, wheel-install and publication gates. A source merge into engine main does not publish a PyPI package. The scientific report has independent authorship and repository/DOI checks, and owner acceptance follows delivery evidence. No social publication is part of deployment; diffusion materials remain private drafts.

Do not claim live completion until the exact deployed commit and served manifest have been observed. Current acceptance status is recorded in the product's design and management records, not inferred from an HTTP 200 alone.
