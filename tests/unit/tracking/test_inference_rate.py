import pytest
from tools.pi_tracker.inference_rate import InferenceRate


def test_rate_limit_and_no_catch_up_after_slow_inference():
    now = [0.0]
    rate = InferenceRate(2, clock=lambda: now[0])
    assert rate.delay() == 0
    rate.started()
    now[0] = 0.25
    assert rate.delay() == 0.25
    now[0] = 0.9  # late inference should not trigger a burst of queued work
    assert rate.delay() == 0
    rate.started()
    assert rate.delay() == pytest.approx(0.5)


def test_default_does_not_change_existing_inference_cadence():
    rate = InferenceRate(clock=lambda: 1.0)
    rate.started()
    assert rate.delay() == 0


@pytest.mark.parametrize("fps", [-1, float("inf"), float("nan")])
def test_invalid_rates_rejected(fps):
    with pytest.raises(ValueError):
        InferenceRate(fps)
