import numpy as np
import pytest
from pipeline.control import predict_states


def test_predictor_retains_input_and_physical_dynamics():
    initial = np.array([1.6, 0.0])
    controls = np.array([-1.0, -1.0, 0.0])
    states = predict_states(initial, controls)
    np.testing.assert_allclose(states, [[1.58, -0.2], [1.52, -0.4], [1.44, -0.4]])
    np.testing.assert_array_equal(initial, [1.6, 0.0])
    assert predict_states([0, 0], []).shape == (0, 2)
    # A diagnostic predictor must expose a bad actuator request instead of repairing it.
    assert predict_states([0, 0], [2])[0, 1] == pytest.approx(0.4)


@pytest.mark.parametrize("initial,control,dt", [([0], [1], .2), ([0, 0], [np.nan], .2),
                                             ([0, 0], [1], True), ([0, 0], [1], 0)])
def test_adversarial_predictor_rejects_invalid_inputs(initial, control, dt):
    with pytest.raises(ValueError):
        predict_states(initial, control, dt)
