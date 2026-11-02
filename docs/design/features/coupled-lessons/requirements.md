# Requirements: directional group-peak worked lessons

The existing eight lessons and their SoftQP 0.1.0 environment/results remain historical evidence.
An additional advanced EN/ES lesson calls the actual published SoftQP 0.2.0 methods through an
explicit external-interpreter boundary. It demonstrates algebra, exact equivalent formulations,
physical row-unit covariance and the complete negative registered result; it never reruns the
registered 210-instance timing campaign or substitutes a notebook-defined solver.

| ID | Requirement | Gate |
|---|---|---|
| CL-001 | THE lesson bridge SHALL invoke an explicitly configured external SDK0.2 interpreter with bounded input, timeout and output; reject malformed/nonfinite requests, missing/internal runtimes, dependency drift and invalid envelopes before accepting numerical data. | `tests/test_coupled_lessons.py::test_adversarial_external_lesson_boundary` |
| CL-002 | THE actual worker SHALL execute native, compact-epigraph and directional row-split methods on the same authored original problem, preserve every method state and check returned original-space metrics independently. Unsupported quadratic row-split cells SHALL remain incompatible with a reason. | `tests/test_coupled_lessons.py::test_adversarial_real_methods_share_the_original_objective` |
| CL-003 | THE lesson SHALL demonstrate reciprocal conversion of original rows/bounds and directional scales across units without changing the original optimum or price. Its small worked cases SHALL remain distinct from the frozen scientific inventory. | `tests/test_coupled_lessons.py::test_adversarial_directional_row_unit_covariance` |
| CL-004 | THE EN/ES notebooks SHALL contain at least five genuine calls to the bridge, derivations, intermediate results, comparison, two interpreted figures, exercises, sources and an evidence-bound negative conclusion. Both SHALL execute in fresh kernels and receive independent review. | `tests/test_coupled_lessons.py::test_adversarial_coupled_curriculum_and_evidence_identity` |
| CL-005 | THE scientific-summary reader SHALL require the exact independently accepted summary bytes, preserve the144-instance population, six seed clusters, nine failed pairs and negative criterion, and never claim that reading a summary reproduces raw-trial bootstrap inference. | `tests/test_coupled_lessons.py::test_adversarial_coupled_curriculum_and_evidence_identity` |

Full independent notebook review and fresh-kernel unchanged-output checks are acceptance gates in
addition to these behavioral tests. Publication of the negative study does not establish novelty,
timing superiority or product scientific qualification.
