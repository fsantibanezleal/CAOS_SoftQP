# Numerical test profiles

The ordinary app consumes the public `softqp==0.1.0` wheel. Its local regression
uses `requirements-precompute.txt` and `requirements-dev.txt`. The advanced teaching
bridge additionally needs an explicitly selected external SDK2 interpreter from
`docs/teaching/coupled/requirements.txt`. Configure `SOFTQP_COUPLED_PYTHON` and an
external `CAOS_TEMP_ROOT` to exercise its genuine method/resource controls.

Three positive controls intentionally require the exact clean source revision of
the original registered study. They are the one-instance line-ending export check
and two stream tests using a shared 32-frame numerical fixture. Their prerequisite
is revision `d0c69ed974d577ba02adbd4806332270d9425651` with clean source identity,
not merely distribution version 0.1.0. In a public-wheel environment they skip
explicitly before any historical scientific work, naming expected/observed identity.
Wrong, missing, dirty and unknown-cleanliness source refusals always run and prove
that no generation, oracle or numerical workspace is reached.

Create a separate external environment from the exact historical profile in
`experiments/separable-v1/requirements.txt` to run those positive controls. This
profile builds the historical native source and requires its documented native
build tools; it does not replace the app, notebook or coupled SDK environments.

```bash
"$HISTORICAL_PYTHON" -m pytest tests/test_softqp_stream.py \
  tests/test_softqp_campaign.py::test_export_bytes_are_lf_on_every_platform
"$COUPLED_PYTHON" -m pytest tests/coupled
```

The complete regression claim combines the full ordinary-profile suite with the
actual separate historical-source positives and the complete SDK2 suite. Missing
prerequisites are visible skips, never accepted scientific results. No test output
is promoted into either frozen campaign or used to recalculate its published timing
endpoint. All test writes remain in isolated temporary paths.
