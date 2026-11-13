# Design: shared-shell routes, executive context and readable documentation

This current design reconciles the existing web composition; it does not create a pre-code acceptance history. The web is a research companion to the native numerical product. Its entry explains the operational problem before technical detail, and its workbench presents actual recorded or locally imported results with an explicit computation lane.

## Route composition and source identity

`frontend/src/App.tsx` composes `AppShell`, `CitationsProvider`, `Landing` and `STANDARD_ROUTES` from the pinned shared shell. Product name, repository, license and visibility come from `product.json`; build/version identifiers are injected from the build configuration rather than manually repeated in components. The six route labels retain App, Introduction, Methodology, Implementation, Experiments and Benchmark order. Root and unknown paths use the shared landing behavior, while the workbench remains at `/app` and legacy App links retain their query/hash context.

The research pages and workbench are separate lazy imports behind a Suspense status. This keeps route-independent shell code small while the scientific route loads its own data and rendering dependencies. A pending state is labelled, not a fabricated result. `frontend/scripts/materialize-routes.mjs` produces static route entries and a real 404 document so direct navigation is not mistaken for a successful host fallback.

## Executive and technical documents

`content/executive.json` is validated by the shell's executive schema and rendered through `ExecutiveView` in `frontend/src/pages/Introduction.tsx`. The executive view opens first; the technical view is a separate second view. Its sourced claims, role-oriented problem context and three bilingual themed illustrations remain data for the shared renderer, not a custom promotional header. The pain and proposal illustrations share a setting so the change being proposed can be read visually.

The five documentation pages use the shared full-width document layout. Equations, citations, references and theme-aware diagrams are authored content inside that structure. The product does not replace the shell's navigation, focus frame, typography or theme tokens with private CSS. Flip-card writing limits and carousel behavior remain shared component constraints, measured in both languages and at narrow widths rather than assumed from source length.

## Focus, motion and availability

Workbench Focus mode is supplied by the shell and entered through its actual focus control. The case, group and selected view survive entry and either exit. `frontend/scripts/gate.mjs` refuses pass-through arguments that would redirect Focus checks away from the real App; a normal workbench cannot waive simulation Focus by editing a command line. A genuine surface waiver would require the matching product and SDD declarations.

Animated illustrations explain a finite change and carry a reduced-motion final frame. `scripts/check_svg_animation.py` and the shell's measured browser gate check the supported animation boundary; an unbounded decorative loop is not an accepted alternative. Current visualization catalog, linked analytical views and story obligations add to these older route/document minima and require their own actual browser review. Passing a structural floor does not establish those newer interactions.

The browser consumes typed, checksummed artifacts and explicit readiness. A missing body, HTML instead of JSON or an unreadable readiness document preserves a meaningful error/unknown state. It is not an empty successful chart. Architecture diagrams come from `frontend/src/architecture/` and are imported inline so theme variables repaint with the shell.

## Integration guards and verification

WB-006 through WB-013 map executive data, illustrations, route order, full-width documents, cards and motion to actual Introduction/App/content tests and the browser gate. WB-014/WB-015 map Focus and App-kind semantics to `frontend/src/gate-script.test.ts` and the guard plants. WB-016 covers suffixless tracked text in `scripts/check_content_standards.py`; WB-017 covers the producer/consumer responsibility of non-JSON catalog documents; WB-018 checks exact npm alias pins against the lock and technology table.

Hand-written shell chrome, an unlabeled stale view and a fake live solve were rejected because each hides the product's actual boundary. [Tasks](tasks.md) links every web requirement to its dependency and production surface. [Validation](validation.md) retains hostile route/animation/focus/type cases. Acceptance also reads the measured captures in both themes and languages; source tests alone do not establish readable layout or deployed identity.
