# Coupled lesson boundary and sizing

The notebook kernel keeps its reviewed SoftQP0.1 environment. A genuine pipeline entrypoint,
`pipeline.coupled_lessons.run_comparison`, dispatches the same checked request through stdin to
an explicit `SOFTQP_COUPLED_PYTHON` outside the checkout. The numerical methods remain in the
published SoftQP0.2 distribution, not in notebook-defined replacements. Both profiles retain
their exact existing pins; the bridge does not install or change either environment.

The authored worked problem has two original variables, two priced interval rows and one hard
equality. Its three profiles are native, compact epigraph and directional row-split GSP. Linear
and quadratic prices, unequal directions and reciprocal row-unit conversions are compared using
the same input. These are instructional method executions, not extra registered trials, timing
benchmarks or additions to the scientific case count. No timing values enter notebook conclusions.

One request is bounded to finite prices/scales and a positive row conversion; output is bounded
to64KiB, exactly three method rows and two-element decision vectors. Each process has a30-second
timeout and an empty stdin beyond the canonical JSON request. Standard output contains one JSON
envelope, bound to canonical input SHA and worker source SHA. The envelope includes exact SDK
version, states/reasons, original metrics, decision vectors and formulation dimensions. No raw
study archive is needed to run the small example. Native/epigraph candidates must pass existing
independent original-space checks; unsupported row-split quadratic cells retain incompatibility.

The new versioned exchange schema has real producer/consumer controls, a genuine generated example
after implementation, a fixture/swap adversary and explicit offline missing-data readiness. It
does not create a coupled browser replay adapter or mark any archived campaign as deployed.

A compact copy of the accepted coupled summary in docs is byte-pinned to its existing independent
review. The runner already copies docs and data-pipeline into its external execution sandbox.
The lesson reads that accepted summary once for evidence; it explicitly distinguishes inspection
from reproducing all raw-trial inference, which requires the separately archived dataset.

An additional level-four notebook in the existing topic, mirrored in EN/ES, contains at least
five actual bridge calls, at least800 explanatory words, two interpreted figures, derivations,
comparison, limitations, exercises and primary sources. The product method registry names the
real bridge entrypoint, the design declares the already implemented directional candidate as
a separate proposed-method claim with its failed acceptance criterion, and its independently
published negative manuscript covers that claim. No success or priority is inferred from either.

## Exact worked problem and units

The original decision is x=(x1,x2) in metres. Fix P=I2, q=(-3,2),
A=[[1,0],[0,1],[1,1]], l=(-1,-1,0), u=(1,1,0). The third row is a hard
equality, x1+x2=0; only the first two rows belong to the one priced group.
P has objective-unit/metre-squared coefficients and q has objective-unit/metre
coefficients. Let r=(x1-clip(x1,-1,1),x2-clip(x2,-1,1)). The group peak is
t=max(c1+ max(r1,0),c2+ max(r2,0),c1- max(-r1,0),c2- max(-r2,0)), where
c-=(1,1.5) per metre and c+=(upper_scale,1) per metre. Thus t is dimensionless.
The price is linear*t + quadratic*tÂ²/2 in objective units. The soft-block box
is C_soft=[-1,1]Â²; hard equality feasibility is imposed separately and is never
included in a soft infimal-convolution identity.

The parameter map fixes linear/quadratic in [0,10], upper_scale in [0.25,4]
and row_scale d in [0.01,100]. Convert D=diag(d,d,1), A'=D*A, l'=D*l,
u'=D*u and c'Â±=cÂ±/d on the two soft rows. Then r'=D_soft*r and t'=t,
so x and the objective are invariant. Multiplying rows without reciprocal scales
defines a different penalty and is the deliberate negative covariance control.
The worked configurations use base linear0.6/quadratic0, a quadratic-only price,
unequal upper directions, and row conversions0.01/100. They are instructional
examples, not additions to the registered scientific population.

## Process, runtime and source admission

An explicitly supplied executable may be a correctly resolved external directory
alias, but must identify a separate Python3.12 virtual environment outside the
checkout. There is no PATH/internal fallback or implicit installation. Kernel
PYTHONPATH/PYTHONHOME are removed; Python isolated mode selects the external
environment. The bridge separately verifies installed SDK Python/native/METADATA
bytes against a manifest at docs/teaching/coupled/public-sdk-files.json derived from SHA-256-verified public0.2.0 wheels (14 Windows and13 Linux runtime/METADATA files per published CPython3.12 wheel), plus
the exact declared profile pins. Envelope sdk_version alone is never evidence.
Caller pre/post snapshots bind the worker, schema, SDK manifest and actual package
files; drift is a refusal. A fresh external cache prefix and bytecode-disabled
execution prevent writes into either package environment.

Each call allocates a unique scratch directory under absolute external CAOS_TEMP_ROOT.
Its canonical request, stdout and stderr stay there and are removed after owned
process cleanup. Both output files are polled while the worker runs; either exceeding
64KiB is a refusal. Worker execution has a30-second wall deadline; it is followed
only by at most three additional seconds of owned cleanup, never an unbounded inherited-pipe wait. A Windows
worker is created suspended, assigned to a non-breakaway kill-on-close Job Object,
then resumed; closing/terminating that job covers descendants even if the launcher
exits. POSIX uses a separately owned process group. Completion, timeout, malformed
output and every failure close the owned group before temporary files are removed.
Cleanup failure is explicit and retains recovery paths; unrelated processes are
never addressed. Tests include descendant processes retaining stdout/stderr after
their immediate parent exits and an unrelated control process.

The operating-system mechanisms follow the primary references:
[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[suspended creation](https://learn.microsoft.com/en-us/windows/win32/procthread/suspending-thread-execution)
and [ResumeThread](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-resumethread).

The schema requires each of native, epigraph and row-split-gsp exactly once.
Accepted rows require finite candidate fields, nonnegative peak/hard/KKT metrics
and a null reason. Accuracy-rejected rows keep complete finite candidates and a
reason. Incompatible/failed rows require a reason and null candidate fields.
Structural validity is followed by input/source/package identity and numerical
acceptance; examples never stand in for execution of the actual methods.

The caller fingerprints the actual files in the explicitly selected external environment before and after execution. The worker independently verifies the same manifest and exact nine-distribution profile before native setup. The manifest retains public wheel filenames and their verified PyPI SHA-256 values; no package source is copied into the product.

The external notebook sandbox receives exact copies of the public SDK fingerprint manifest, the nine-distribution study profile and the accepted summary under docs/teaching/coupled. These are byte-identical copies of their original authorities, bound by the bridge and adversarial tests; they are never alternative mutable profiles. Canonical input is at most4KiB before worker creation.

On Windows, a direct native base executable is required. Store AppExecutionAlias broker launchers can create a runtime outside the launchers Job Object; their virtual environments are explicitly refused before execution. The didactic SDK2 environment is separately created from a direct Python3.12 executable with the unchanged nine pins. Historical Store-based study and notebook environments remain untouched. This is a process-ownership restriction, not a different numerical profile.
