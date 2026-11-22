# Dependency graph and convergence: physical units

Literal discovery must remain stable before a reviewed unit inventory can bind it. A physical covariance control and original-space result admission then test dimensions at two different boundaries. This is a current reconciliation with the existing immutable numerical code.

## Dependency sequence

| Unit | Requires | Requirements | Implementation responsibility | Production and test files |
|---|---|---|---|---|
| U1 | None | [PU-001](requirements.md) | Bind owned AST literals to reviewed quantities, units and context | `scripts/check_unit_constants.py`; `docs/units/float-constants.json`; `tests/test_physical_units.py` |
| U2 | U1 | [PU-002](requirements.md) | Independently reconstruct and convert the actual control prediction | `data-pipeline/pipeline/control.py`; `data-pipeline/pipeline/softqp_cases.py`; `tests/test_physical_units.py` |
| U3 | U1, U2 | [PU-003](requirements.md) | Refuse wrong-unit or falsely reported original-space case results | `scripts/local/softqp_adapter.py`; `tests/test_local_softqp_admission.py` |

## Exact requirement gates

Each requirement retains its own positive/behavioral gate and its distinct hostile check in [validation](validation.md). This table is an interface-to-proof map; it makes no claim that an unobserved command passed.

| Requirement | Dependency unit | Required gate from the current specification | Current convergence boundary |
|---|---|---|---|
| [PU-001](requirements.md) | U1 | `tests/test_physical_units.py::test_adversarial_float_inventory` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [PU-002](requirements.md) | U2 | `tests/test_physical_units.py::test_adversarial_control_unit_covariance` | Implementation mapped; current gate execution is a separate acceptance obligation. |
| [PU-003](requirements.md) | U3 | `tests/test_local_softqp_admission.py::test_adversarial_input_settings_and_objective_parity`, `tests/test_local_softqp_admission.py::test_adversarial_rehashed_incomplete_inventory_is_refused` | Implementation mapped; current gate execution is a separate acceptance obligation. |

## Current convergence

The inventory and dimensional controls target concrete source and original coordinates. The gate results themselves must be observed; adding a unit string is not a physical proof. Tolerances, populations and frozen scientific modules remain unchanged, and no universal unit-interval output range is imposed on a soft-QP decision.

The design in [design.md](design.md), all current requirement rows and their validation rows are explicit. Structural document checks verify these links and identifiers. They do not substitute for executing the functional gates or for independently reviewing a changed numerical or visual result.
