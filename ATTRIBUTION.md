# Attribution

The source-faithful building-energy case C13 uses the synthetic model authored by
the OSQPSlack Project Contributors, copyright 2026, distributed under the MIT
License. The exact source is
[energy_hub.py at commit 2e5d5ce](https://github.com/A2R-Lab/OSQPSlack/blob/2e5d5ce8968207d0838d08942a8af7bdda64f634/osqpslack/energy_hub.py).
The [complete MIT notice](data/licenses/OSQPSlack-MIT.txt) is retained.

Only the attribution comment and penalty-helper import differ in the adapted
source. C14 and C15 deliberately replace the original mixed penalties while
retaining its building structure. They cannot be interpreted as reproductions of
the original optimization objective. These are synthetic models, not measured
building records. Details and source hashes are in
[building-model provenance](docs/energy-provenance.md).

Generalized slack projection follows the work of Roland Schwan, Thomas Lew and
Brian Plancher, [arXiv:2610.35631](https://arxiv.org/abs/2610.35631). The native engine
preserves the upstream software notices in its separate public distribution.
DAQP, OSQP, ElastiQP and the fixed-equation FlexQP reconstruction are attributed
in the [research sources](docs/research.md) and manuscript bibliographies. A
reconstruction is not a reproduction of unavailable learned weights or data.

The coupled sparse problems and hourly two-zone forecasts are independently
authored synthetic cases. They are distinct from the attributed quarter-hourly
C13 building model and do not represent field performance.
