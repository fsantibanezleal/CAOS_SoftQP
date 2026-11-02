"""A real native stream, with independent references and plant invariants."""

import json
from pathlib import Path
import numpy as np
import pytest
from pipeline.softqp_stream import run_stream
from historical_profile import require_registered_engine


@pytest.fixture(scope="module")
def stream():
    require_registered_engine()
    return run_stream()


def test_c12_complete_pairing_and_accuracy(stream):
    assert len(stream["frames"]) == 32
    assert stream["counts"] == dict(accepted=192, incompatible=64, failed=0, **{"accuracy-rejected": 0})
    assert len(json.dumps(stream, allow_nan=False)) > 1000
    for frame in stream["frames"]:
        assert {(r["method"], r["mode"]) for r in frame["runs"]} == {
            (m, mode) for m in ("lifted", "generalized", "asymmetric", "daqp") for mode in ("cold", "warm")
        }
        for run in frame["runs"]:
            if run["state"] == "accepted":
                assert run["metrics"]["hard_violation"] <= 1e-6
                assert run["normalized_gap"] <= 1e-6
                assert run["result"]["x"][0] == pytest.approx(frame["applied_control"], abs=2e-5)
                assert run["workspace_setup_seconds"] is not None if (
                    run["mode"] == "warm" and frame["frame"] == 0
                ) else run["workspace_setup_seconds"] is None


def test_adversarial_stream_dynamics_and_disturbances(stream):
    previous = np.array([1.6, 0.0])
    for frame in stream["frames"]:
        expected = previous + np.array([0.0, {8: 0.8, 20: -0.6}.get(frame["frame"], 0.0)])
        np.testing.assert_allclose(frame["state"], expected, atol=1e-14)
        control = frame["applied_control"]
        assert -1.0 <= control <= 1.0
        next_state = np.array([[1, 0.2], [0, 1]]) @ expected + np.array([0.02, 0.2]) * control
        np.testing.assert_allclose(frame["next_state"], next_state, atol=1e-14)
        assert frame["oracle_horizon_cost"] == pytest.approx(
            frame["oracle_objective"] + frame["objective_constant"]
        )
        previous = next_state


def test_protocol_frozen_before_campaign():
    root = Path(__file__).resolve().parents[1]
    protocol = json.loads((root / "docs/design/experiments-v1.json").read_text(encoding="utf-8"))
    assert protocol["engine_source"] == "d0c69ed974d577ba02adbd4806332270d9425651"
    assert set(protocol["seeds"]["development"]).isdisjoint(protocol["seeds"]["heldout"])


def test_adversarial_stream_refuses_an_unpinned_engine(monkeypatch):
    import pipeline.softqp_stream as stream_module

    monkeypatch.setattr(stream_module, "environment", lambda: dict(engine_revision=None, engine_source_dirty=None))
    with pytest.raises(RuntimeError, match="exact clean native source"):
        stream_module.run_stream()
