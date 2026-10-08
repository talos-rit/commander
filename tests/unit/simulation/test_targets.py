import pytest

from src.simulation.targets import CylindricalPoseMm
from src.simulation.targets import CartesianPoseMm


@pytest.mark.parametrize(
    ("theta", "radius", "expected"),
    [(0, 420, (420, 0)), (90, 420, (0, 420)), (180, 420, (-420, 0)), (270, 420, (0, -420)), (35, 0, (0, 0))],
)
def test_cylindrical_conversion_uses_documented_robot_frame(theta, radius, expected):
    result = CylindricalPoseMm(theta, radius, 690, -15, 5).to_cartesian()
    assert (result.x_mm, result.y_mm) == pytest.approx(expected)
    assert result.z_mm == 690
    assert (result.pitch_degrees, result.roll_degrees) == (-15, 5)


@pytest.mark.parametrize("radius", [-1, float("inf"), float("nan")])
def test_cylindrical_rejects_invalid_radius(radius):
    with pytest.raises(ValueError):
        CylindricalPoseMm(0, radius, 0)


@pytest.mark.parametrize("factory", [
    lambda: CartesianPoseMm(float("nan"), 0, 0),
    lambda: CartesianPoseMm(0, 0, 0, pitch_degrees=float("inf")),
    lambda: CylindricalPoseMm(float("nan"), 0, 0),
    lambda: CylindricalPoseMm(0, 0, 0, roll_degrees=float("-inf")),
])
def test_target_types_reject_non_finite_inputs(factory):
    with pytest.raises(ValueError):
        factory()
