# Contract fixtures only

These files exercise U1 schema, math, provenance and serialization admission. They are not registered scientific data, solver observations, measured performance, trained checkpoints, actual torch initialization or real runtime RNG/optimizer states.

accepted-design/ preserves the exact R4 manifest and the machine/keyset inputs needed by admission. Its manifest is e098010809f8b4cbb57f04e70279bf0b3f4aa90994be8a1ae022bbb52a4c7fb0. No sealed source or scientific study is changed.

provider.py writes hand-defined, explicitly provider-labelled fixtures only to an external test root using the real write_artifact/read_artifact entry points. provider-tree/ is the exact copied linked JSON/numeric fixture tree plus an explicit fixture-only context configuration. Model .f64 files contain untrained zeros; .u8 files demonstrate opaque numeric serialization only. Their labelled purpose cannot enter production admission, and no fixture counts toward the method/model/scientific bar. The graph provider exercises52098declared parameter coordinates, labels/class weights and threshold calibration; no network or solver runs.

missing-examples/ contains one real serialized missing record for every boundary. Each has null payload and an explicit reason. Test consumers copy fixtures outside the checkout before reading; production consumers reject the fixture lane. The acceptance matrix is docs/contracts/learning-catalog.md. Complete scientific producers, runtime parity, genuine training/resume/inference and product integration remain pending independent downstream gates.
