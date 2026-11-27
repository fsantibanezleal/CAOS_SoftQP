# Excluded scientific runtime fixtures

The native-label and training tests use an explicitly nominated external SDK installation. Set these absolute paths together before running the tests:

- `SOFTQP_SDK45_FIXTURE_PYTHON` points to the approved SDK-only Windows interpreter.
- `SOFTQP_SDK45_FIXTURE_PROFILE` points to the approved 45-package profile directory.
- `SOFTQP_SDK45_FIXTURE_WHEEL` points to the exact published SDK 0.3.0 Windows wheel.

The test independently pins the SDK release, wheel, profile, checker and defaults. The API discovers the selected interpreter's base executable. No SDK or dependency is installed by the tests.

The full 49-package native qualification fixture additionally expects:

- `SOFTQP_NATIVE49_FIXTURE_SNAPSHOT` points to the external, frozen qualification root containing `profile` and `source`.
- `SOFTQP_NATIVE49_FIXTURE_PYTHON` is the approved installed 49-package interpreter.
- `SOFTQP_NATIVE49_FIXTURE_TOOLS` is the separately sealed test-tools directory.
- `SOFTQP_NATIVE49_FIXTURE_PROFILE_SHA256` is the independently expected provenance digest recorded when the snapshot was frozen.
- `SOFTQP_NATIVE49_FIXTURE_BASE_PYTHON` optionally nominates the base interpreter. Otherwise the test uses the running harness's base interpreter.

With no variables from a nomination group, tests that require that group skip with the names to set. An incomplete group, invalid path, or mismatched pin fails. Source and lightweight process controls run without either external nomination. These fixtures are excluded from scientific execution.
