# Worked optimization lessons

The [English](en/README.md) and [Spanish](es/README.md) trees contain five mirrored lessons on the product's authored inputs. They progress through scalar prices, hard actuator policy, published numerical methods and the registered computational hypothesis. Every lesson calls the actual methods rather than substituting a baked-result inspection for optimization.

## Environment and execution

Use Python 3.12 and the exact requirements in `requirements.txt`. The separate native distribution [softqp 0.1.0 is published on PyPI](https://pypi.org/project/softqp/0.1.0/). The ordinary lessons use its public Windows wheel; the directional lesson invokes the separate pinned 0.2.0 runtime through the guarded teaching bridge. The recorded experiment uses the exact historical source revision in its protocol, independently of later packaging metadata.

```bash
python -m pip install -r notebooks/requirements.txt
python scripts/run_notebooks.py
python scripts/check_notebooks.py
python scripts/run_notebooks.py --check
```

The runner uses `.venv-notebooks`. Set `CAOS_TEMP_ROOT` to the device's external temporary directory before the fresh-kernel check; no repository-local temporary tree or ambient system temp fallback is allowed. The runner alone writes outputs and strips volatile metadata. All figures need labeled axes, units and a prose interpretation in the notebook's language.

The side-specific lesson includes one deterministic reproduction of the original frozen endpoint from the complete canonical export. The directional lesson reads its separately accepted summary without repeating the raw-trial inference. Both compute fresh educational parameter sweeps through the real numerical methods, explicitly outside either registered timing campaign. Neither selects a favorable evaluation subset or changes the unsuccessful 10% criterion.

## Review boundary

The [notebook guide](../docs/guides/08_notebooks.md) sets the worked-lesson bar and requires review by someone other than the author before release. Static floors and fresh execution are necessary evidence, not independent editorial or scientific review. The source report, package publication and product release have their own acceptance gates.

All eight lessons passed [independent curriculum review](../docs/notebook-review.md) after correcting control-interval timing in two figures and Spanish method display names. That review does not establish the rejected timing hypothesis or qualified product-release acceptance.

The fifth lesson teaches directional shared peaks and reciprocal physical row scaling through actual public SDK0.2 methods. Keep the notebook kernel pins unchanged. Install docs/teaching/coupled/requirements.txt into a separate external CPython3.12 environment created from a direct native executable; set SOFTQP_COUPLED_PYTHON to its absolute interpreter and CAOS_TEMP_ROOT to an existing external scratch directory. Windows Store broker bases are refused before execution. The lesson bridge uses isolated startup without site hooks, verifies installed SDK/source identities and retains unsupported quadratic row-split states. It inspects the exact accepted summary while explicitly distinguishing this from raw-trial bootstrap reanalysis. Independent acceptance of these two new lessons is recorded separately from the historical eight.

## Coverage and lesson depth

The coverage map in `coverage.json` connects all seven declared methods, eighteen contracts, the five actual pipeline responsibilities and the public method package to the lessons that teach them. A mapped contract is read or explained with its fields, units, producers, consumers and missing-data boundary; a schema fixture is never presented as a measured observation. There is no invented training stage. Each advanced lesson derives its equations, sweeps a meaningful input, explains where the method changes or fails and teaches adaptation to another input. The ten executed notebooks contain 28 interpreted figures. Independent substantive review and fresh-kernel byte comparison are separate release gates.
