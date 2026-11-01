# Worked optimization lessons

The [English](en/README.md) and [Spanish](es/README.md) trees contain four mirrored lessons on the product's authored inputs. They progress through scalar prices, hard actuator policy, published numerical methods and the registered computational hypothesis. Every lesson calls the actual methods rather than substituting a baked-result inspection for optimization.

## Environment and execution

Use Python 3.12 and the exact requirements in `requirements.txt`. The separate native distribution [softqp 0.1.0 is published on PyPI](https://pypi.org/project/softqp/0.1.0/). All eight lessons pass the copied-repository unchanged-output check using its public Windows wheel. The recorded experiment uses the exact historical source revision in its protocol, independently of later packaging metadata.

```bash
python -m pip install -r notebooks/requirements.txt
python scripts/run_notebooks.py
python scripts/check_notebooks.py
python scripts/run_notebooks.py --check
```

The runner uses `.venv-notebooks`. Set `CAOS_TEMP_ROOT` to the device's external temporary directory before the fresh-kernel check; no repository-local temporary tree or ambient system temp fallback is allowed. The runner alone writes outputs and strips volatile metadata. All figures need labeled axes, units and a prose interpretation in the notebook's language.

The final lesson requires the complete canonical experimental export and recomputes the primary statistic from every raw observation. It stops if only development evidence is present. It preserves the failure of the registered 10% improvement criterion rather than selecting a favorable evaluation subset.

## Review boundary

The [notebook guide](../docs/guides/08_notebooks.md) sets the worked-lesson bar and requires review by someone other than the author before release. Static floors and fresh execution are necessary evidence, not independent editorial or scientific review. The source report, package publication and product release have their own acceptance gates.

All eight lessons passed [independent curriculum review](../docs/notebook-review.md) after correcting control-interval timing in two figures and Spanish method display names. That review does not establish the rejected timing hypothesis or qualified product-release acceptance.
