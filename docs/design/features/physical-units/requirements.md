# Requirements: dimensional constants and physical answers

The numerical studies are immutable. These checks describe their existing declared
coordinates; they do not change a solver, scientific tolerance, score or population.
Optimization decisions can exceed a soft bound. A universal prediction range or
unit-interval gate would be mathematically inappropriate here.

| ID | Requirement | Gate |
|---|---|---|
| PU-001 | Every float literal in an owned numerical method, case, diagnostic or analysis module SHALL have an AST-bound inventory entry naming its quantity, unit and rationale; additions, changes, removed entries and missing units SHALL fail until reviewed. | `tests/test_physical_units.py::test_adversarial_float_inventory` |
| PU-002 | Authored control predictions SHALL preserve physical position, velocity, acceleration and time covariance without clipping; a wrong time or acceleration conversion SHALL be detected by the independent dimensional control. | `tests/test_physical_units.py::test_adversarial_control_unit_covariance` |
| PU-003 | Shipped per-case metrics SHALL be recomputed from the authored original problem, preserve row units and hard/soft policy, and pass the unchanged original accuracy bands; wrong-unit metadata or a falsely reported hard residual SHALL be refused. | `tests/test_local_softqp_admission.py::test_adversarial_input_settings_and_objective_parity`, `tests/test_local_softqp_admission.py::test_adversarial_rehashed_incomplete_inventory_is_refused` |

The public SDK is a separately versioned dependency. Its byte fingerprints and
installed-source identity gates bind it to the reviewed implementation; this
inventory governs all numerical modules owned by this app, including frozen study
code. It never edits the frozen modules to add comments or change constants.
