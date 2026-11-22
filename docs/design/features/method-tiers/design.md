# Design: method declarations, teaching coverage and scientific claims

This document reconciles the current declarations with their executable guards. It describes how implementation coverage is represented, rather than claiming that the document existed before the engine was written. Internal classification is necessary for design and coverage; it is not a reader-facing label or a claim that a proposal has outperformed established methods.

## The executable ladder

`docs/design/SDD.md` owns the method ladder's identifiers, internal category, concrete method name, acceptance criterion and gate. The implementation includes explicit lifting, published generalized slack projection, DAQP, fixed-parameter FlexQP, ElastiQP and the two proposed updates. `scripts/check_sdd.py` rejects a missing/malformed ladder, unknown categories, duplicate identifiers, empty criteria and a missing link between a proposed-method row and the SDD's proposal section. A validation protocol alone does not satisfy a numerical method row.

The actual numerical paths remain in the separately published `softqp` dependency and the named pipeline modules. The metadata does not provide a plug-in that can fabricate a method at display time. Compatibility and original-space acceptance belong to the numerical feature; this feature checks that a promised method is not lost between design, teaching, manuscripts and public naming. Scientific acceptance remains governed by the registered hypothesis, and both current timing criteria remain unsuccessful.

## Notebook and publication boundaries

`product.json` declares method entrypoints, method packages and manuscript entries. `scripts/check_notebooks.py` reads the SDD's published-method rows and requires matching `caos.methods` declarations in level-three notebooks in each language. That specialized field does not list the ordinary lifted baseline on a level-two lesson. The broader `notebooks/coverage.json` maps all methods and contracts to substantive teaching; an identifier is not evidence unless the notebook actually executes and explains the method.

`scripts/check_manuscripts.py` validates the manuscript entry kind, concept DOI, supported fields, title, version and covered proposal identifiers. A product requires a technical report; every proposed method has a research manuscript, with closely related proposals sharing a paper only under full separate derivation/experiment coverage. The declaration is not a deposit. The opt-in `--zenodo` read checks the actual concept and latest published version; ordinary CI remains offline. The `--release` check enforces report currency when the release changes a method, source or result. Documentation-only changes are assessed against their actual scope, never used to rewrite scientific observations.

The report and preprint have separate stable concepts. Reusing a concept twice or naming a claim absent from the SDD is invalid. Missing or incorrectly typed metadata fails instead of quietly omitting the publication from a product's coverage.

## Public naming and invalid data

`scripts/check_internal_names.py` inspects manuscript sources, notebook markdown/code text/outputs, indexes, README, product titles and app strings. Reader-facing surfaces name each numerical method and use Comparison and Evidence for the relevant lesson sections. Internal category words and claim identifiers remain in the design, configuration metadata and gates. Bibliographic titles retain their actual published wording; supported exemptions are narrow rather than a reason to suppress a whole document.

Default checks do not contact a service or infer a positive novelty verdict from a version label. A missing SDD ladder is reported by the design guard rather than guessed from notebook labels. A missing or malformed Zenodo response in the explicit online check remains a failed verification. Exact scientific results and publication types continue to be checked by the numerical and manuscript features.

## Alternatives and requirement map

Inferring coverage from citations was rejected: mentioning a solver does not implement or run it. Dropping an unsuccessful proposal was rejected because a negative result remains a research result. Putting internal classifications in titles was rejected because it substitutes a ranking label for the actual method and its supported finding.

MT-001 through MT-003 are exercised by `tests/test_method_tiers.py`; MT-005 by `tests/test_method_tiers_notebooks.py`; MT-006 through MT-009 by `tests/test_check_manuscripts.py`; and MT-010/MT-011 by `tests/test_check_internal_names.py`. Their existing validation rows attack malformed ladders, incomplete language coverage, invented publication metadata and leaked names. [Tasks](tasks.md) states the dependency order. Gate existence and metadata coverage do not independently establish novelty or comparative performance.
