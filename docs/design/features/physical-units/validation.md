# Validation: dimensional constants and physical answers

| requirement | adversarial check | gate |
|---|---|---|
| PU-001 | Plant a new float, change an existing value, remove its unit and rename a numerical module; require refusal with an unchanged valid inventory control. | `tests/test_physical_units.py::test_adversarial_float_inventory` |
| PU-002 | Convert metre/second coordinates to centimetre/millisecond coordinates with reciprocal time and acceleration factors; omit one conversion and prove that predictions disagree. | `tests/test_physical_units.py::test_adversarial_control_unit_covariance` |
| PU-003 | Rehash a record with incorrect input/settings, row metadata or self-consistent wrong-unit decisions; require actual original-space admission refusal, retaining the original complete inventory control. | `tests/test_local_softqp_admission.py::test_adversarial_input_settings_and_objective_parity`, `tests/test_local_softqp_admission.py::test_adversarial_rehashed_incomplete_inventory_is_refused` |
