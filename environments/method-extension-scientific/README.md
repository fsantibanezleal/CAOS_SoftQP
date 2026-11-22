# Scientific product runtime qualification

The proposed Windows AMD64 CPython 3.12.14 environment extends the exact published SDK 0.3.0 CPU profile. All 45 inherited artifact and source identities stay fixed. The product validator adds jsonschema 4.26.0, jsonschema-specifications 2025.9.1, referencing 0.37.0 and rpds-py 2026.9.1. The inherited attrs 26.1.0 satisfies the remaining active dependency. The existing historical product lock retains its own SDK and NumPy pins.

| Artifact | Binding |
|---|---|
| Runtime profile | Inherited engine profile format with exact all-distribution alphabet, locks, source inventories, original defaults, public SDK artifact and all license files |
| Custody manifest | Exact runtime and CPython base file path, size and SHA-256 inventory, Python entrypoint and DLL identities, fixed product source and test fixture file map |
| Runtime observation | Externally expected profile hash, explicit source snapshot digest, stage deadlines, process IDs, actual module/path/native observations and full-scan counts. The document records software qualification only |
| Authority handoff | The authority owner binds the externally approved profile and checker separately. Qualification does not issue I1 approval |

Startup uses isolated no-site CPython. The bootstrap selects the exact environment and source snapshot explicitly. Executable site hooks and user paths stay inactive. The worker redirects bytecode lookup to a new empty path and blocks writes. Cmeel native dependencies use the admitted package layout. Package versions never stand in for live origins. A successful scan qualifies only the observed bytes at that operation. A later scientific operation requires its own supervised fresh scan and active custody or a mutation check spanning all work. A returned software receipt has no reusable authority.

The process gates use independent deadlines for full file scan (600 seconds), imports (180 seconds), and each numerical or reader control (30 seconds). Qualification uses real SDK API calls on excluded controls, plus the existing product contract fixture. Package build metadata, numerical tests and fixture validation carry no experimental output.

## Reproducing the software check

Use an independently expected raw profile SHA-256. Supply the exact installed interpreter, its base executable, the approved source snapshot and the test-only tree. The run directory must be a new external location.

```powershell
& $base -I -S -B "$profile/verify.py" `
  --python $python --base-python $base --profile $profile `
  --source $source --tools $tools --run $newRunDirectory `
  --expected-profile-sha256 $independentlyExpectedProfileSha256
```

The parent checks and holds the CPython base before spawning a suspended owned job. The worker verifies real job membership, confirms the new bytecode prefix is unused, and holds the complete runtime, base, source and test-tool file inventories before admitting imports. It compares the held SHA-256 and size of each wheel RECORD entry against the archived engine profile, and uses the original engine verifier for exact distribution, license and settings metadata. The numerical control process independently checks live defaults, loaded module origins and native image paths. The stage and cleanup receipts remain in the external run directory.

The reviewed host profile pins the exact observed Microsoft-signed Defender image in its own scope. It applies Windows' legacy extension-point mitigation locally to the owned worker. Other external binaries refuse. Operating-system image paths and observed byte digests are retained separately. [Windows process mitigation API](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessmitigationpolicy)

PyG renders a fresh LEConv implementation during its normal operation. The worker permits the approved named render in fresh owned scratch after checking the pinned recipe source files and exact rendered bytes and establishing a write/delete-denying handle. Any other explicit source-loader attempt invalidates the worker even if the library handles the loader error.

The qualification source snapshot cannot dispatch registered generation. A future verified committed snapshot and independent policy are required for the fixed generator bridge. The [batch design](batch-dispatch.md) describes the shared boundary.
