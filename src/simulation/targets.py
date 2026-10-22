"""Hardware-independent Cartesian and cylindrical target value objects."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CartesianPoseMm:
    x_mm: float
    y_mm: float
    z_mm: float
    pitch_degrees: float | None = None
    roll_degrees: float | None = None

    def __post_init__(self) -> None:
        values = (self.x_mm, self.y_mm, self.z_mm, self.pitch_degrees, self.roll_degrees)
        if not all(value is None or math.isfinite(value) for value in values):
            raise ValueError("Cartesian coordinates and optional orientation must be finite")


@dataclass(frozen=True)
class CylindricalPoseMm:
    """Right-handed robot-frame target: theta=0 is +X and grows toward +Y.

    This is deliberately a mathematical convention, not a claim about Bingo's
    physical base-zero convention.  Hardware code must configure/calibrate that
    transform before accepting a real motion command.
    """

    theta_degrees: float
    radius_mm: float
    z_mm: float
    pitch_degrees: float | None = None
    roll_degrees: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.radius_mm) or self.radius_mm < 0:
            raise ValueError("radius_mm must be finite and non-negative")
        values = (self.theta_degrees, self.z_mm, self.pitch_degrees, self.roll_degrees)
        if not all(value is None or math.isfinite(value) for value in values):
            raise ValueError("cylindrical coordinates and optional orientation must be finite")

    def to_cartesian(self) -> CartesianPoseMm:
        theta = math.radians(self.theta_degrees)
        return CartesianPoseMm(
            self.radius_mm * math.cos(theta), self.radius_mm * math.sin(theta), self.z_mm,
            self.pitch_degrees, self.roll_degrees,
        )
