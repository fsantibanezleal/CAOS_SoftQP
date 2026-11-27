# Requirements: the example workbench, end to end

EARS (Mavin et al., RE'09, doi:10.1109/RE.2009.9). Every requirement names the gate that fails when it is violated.

| ID | Requirement | Gate |
|---|---|---|
| EX-001 | WHEN the bake runs a case, THE pipeline SHALL fail if a result metric lies outside the range the case declares, naming the metric. | `tests/test_expect.py::test_a_value_outside_its_range_is_named` |
| EX-002 | THE authored case registry SHALL encode identical scientific inputs for the same case and seed, and exported result inventories SHALL detect a changed byte even when file size is preserved; elapsed-time fields SHALL not be claimed byte-deterministic. | `tests/test_pipeline_smoke.py::test_adversarial_same_seed_bakes_identical_bytes_and_a_changed_byte_of_equal_size_is_seen` |
| EX-003 | IF a test writes into the committed artifacts, THEN THE test session SHALL fail and name the files. | `tests/conftest.py` |
| EX-004 | WHEN an ingestion value is missing, non-numeric, NaN or out of range, THE pipeline SHALL reject the record with its reason. | `tests/test_contract.py::test_adversarial_bad_rows_rejected_not_coerced` |
| EX-005 | THE web SHALL read exactly the keys the pipeline writes, with their types, in every committed artifact. | `frontend/src/lib/contract.test.ts::validates the index, manifest, result and byte inventory` (and, per case, `manifest and trace conform`, over the bake and the provider tree) |
| EX-008 | IF an artifact answers anything but JSON, THEN THE web SHALL raise an error naming the file. | `frontend/src/api/artifacts.test.ts::adversarial: refuses an HTML answer (the host fallback for a missing file)` |
| EX-009 | WHEN a reader opens any route directly, with or without a trailing slash, THE site SHALL answer 200 with that route. | `frontend/scripts/materialize-routes.mjs`, measured by `frontend/scripts/gate.mjs` (G4) |
| EX-010 | WHILE the App route is open at a desktop viewport, THE primary stage SHALL occupy at least 60% of the viewport and at least 80% in Focus. | `frontend/scripts/gate.mjs` (G6) |
| EX-011 | WHEN any registered control changes, THE workbench SHALL change the selection key, and no view SHALL keep an earlier key. | `frontend/scripts/gate.mjs` (G9) |
| EX-012 | THE repository SHALL state its version in VERSION only. | `scripts/check_version_coherence.py` |
| EX-013 | WHEN Context enters Focus, THE workbench SHALL show the selected scientific scene while preserving the Context group; every other Focus group SHALL retain its own selected content. | `frontend/scripts/check-softqp-ui.mjs` |
| EX-014 | WHEN case, scene, method, native result or Focus changes through the workbench or browser history, THE workbench SHALL preserve unrelated live query fields, hash and router state and SHALL restore the corresponding recorded or verified native selection. | `frontend/scripts/check-softqp-ui.mjs` |
| EX-015 | WHILE Context Focus is open, THE Method and costs rail SHALL expose the same native editing, request and verified import workflow using unique control identifiers and an accessible scrolling rail on a short phone viewport. | `frontend/scripts/check-softqp-ui.mjs` |
