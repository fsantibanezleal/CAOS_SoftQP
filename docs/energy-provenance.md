# Building-model provenance

The source-faithful C13 model is adapted from [OSQPSlack energy_hub.py at 2e5d5ce8968207d0838d08942a8af7bdda64f634](https://github.com/A2R-Lab/OSQPSlack/blob/2e5d5ce8968207d0838d08942a8af7bdda64f634/osqpslack/energy_hub.py). The upstream file was retrieved and compared with the app source during implementation.

| Object | SHA-256 of LF UTF-8 source |
|---|---|
| Upstream energy_hub.py | 10c18cd91377cb94fff2febabe0c0d70732ea198e0ea57c6ea289f384b22b2a3 |
| Adapted energy_reference.py | 4819892650ec3ea5884ed3a536fc4c3fca5babf6a6515e0c8c4405f036533be4 |

After normalizing line endings, the complete diff contains two changes: an attribution comment was added, and the import of `osqpslack.penalties` was redirected to the preserved `softqp.reference` helpers. Constants, model dynamics, generated exogenous inputs, constraints and penalty choices are unchanged.

The model has two coupled thermal zones, a 20 kWh battery, HVAC power, battery discharge and grid import over 96 quarter-hour intervals. C13 preserves quadratic comfort, grouped maximum grid overage, elastic battery-health and Huber ramp costs. The [MIT notice](../data/licenses/OSQPSlack-MIT.txt) remains with the product.

C14 and C15 retain the matrices and hard mask but deliberately replace those mixed penalties with authored separable asymmetric costs. They are declared variants and must never be described as reproductions of the published objective. The [case pages](cases/README.md) and original physical row metadata preserve this distinction.
