"""Dimensional falsification without changing frozen study data or tolerances."""

import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("unit_constants", ROOT / "scripts/check_unit_constants.py")
units = importlib.util.module_from_spec(spec)
spec.loader.exec_module(units)


def test_adversarial_float_inventory(tmp_path):
    baseline = json.loads(units.BASELINE.read_text(encoding="utf-8"))
    assert not units.findings(ROOT, baseline)
    shutil.copytree(ROOT / "data-pipeline", tmp_path / "data-pipeline",
                    ignore=shutil.ignore_patterns("__pycache__"))
    path = tmp_path / "data-pipeline/pipeline/control.py"
    original = path.read_text(encoding="utf-8")
    for changed in (original + "\nunreviewed_bound = 0.75\n", original.replace("dt=0.2", "dt=0.3")):
        path.write_text(changed, encoding="utf-8")
        assert units.findings(tmp_path, baseline)
    path.write_text(original, encoding="utf-8")
    assert not units.findings(tmp_path, baseline)
    key = next(iter(baseline["constants"]))
    del baseline["constants"][key]["unit"]
    assert any("missing reviewed unit" in error for error in units.findings(tmp_path, baseline))
    path.rename(path.with_name("renamed_control.py"))
    assert any("module discovery changed" in error for error in units.findings(tmp_path, baseline))


def test_adversarial_control_unit_covariance():
    from pipeline.control import predict_states
    from pipeline.softqp_cases import mpc

    # The real authored MPC uses dt0.2s and initial position1.2m; independently
    # reconstruct its first unconstrained physical trajectory for nonzero controls.
    original = mpc()
    horizon = len(original.q)
    controls = np.linspace(-0.8, 0.7, horizon)
    initial, dt = np.array([1.2, 0]), 0.2
    seconds = np.arange(1, horizon + 1) * dt
    velocity = initial[1] + np.cumsum(controls) * dt
    position = (initial[0] + initial[1] * seconds
                + np.array([np.sum(controls[:k] * (k - np.arange(k) - 0.5)) * dt**2
                            for k in range(1, horizon + 1)]))
    independent = np.column_stack([position, velocity])
    actual = predict_states(initial, controls, dt)
    assert actual == pytest.approx(independent, abs=1e-12)
    # Bind the numerical source's condensed prediction rows and offsets too.
    assert original.A[horizon:] @ controls - original.lower[horizon:] == pytest.approx(
        independent.reshape(-1) - np.tile([-2, -1.5], horizon), abs=1e-12)
    converted = predict_states(initial * [100, 0.1], controls * 1e-4, dt * 1000)
    assert converted / [100, 0.1] == pytest.approx(independent, abs=1e-12)
    wrong_time = predict_states(initial * [100, 0.1], controls * 1e-4, dt)
    wrong_acceleration = predict_states(initial * [100, 0.1], controls, dt * 1000)
    assert np.max(abs(wrong_time / [100, 0.1] - independent)) > 0.1
    assert np.max(abs(wrong_acceleration / [100, 0.1] - independent)) > 100
