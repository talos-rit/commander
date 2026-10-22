"""Traceable controller-coordinate calibrations for the real ER-V twin."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class CalibrationEvidence(str, Enum):
    """Provenance of one independent part of an affine joint calibration."""

    PHYSICALLY_ANCHORED = "physically_anchored"
    PHYSICALLY_VERIFIED = "physically_verified"
    INHERITED_CONTROLLER_CONVERSION = "inherited_controller_conversion"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class JointCalibration:
    """Map an absolute controller coordinate into one URDF joint coordinate.

    ``direction`` is the sign of increasing controller counts in URDF space.
    Keeping both references explicit makes the physical anchor inspectable and
    avoids hiding it in a combined intercept/magic offset.
    """

    joint_name: str
    controller_reference: int
    urdf_reference: float
    counts_per_degree: float
    direction: int
    reference_evidence: CalibrationEvidence
    direction_evidence: CalibrationEvidence
    scale_evidence: CalibrationEvidence
    note: str

    def __post_init__(self) -> None:
        if self.counts_per_degree <= 0:
            raise ValueError("counts_per_degree must be positive")
        if self.direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")

    @property
    def radians_per_count(self) -> float:
        return math.pi / (180.0 * self.counts_per_degree)

    def to_urdf(self, controller_count: int) -> float:
        return self.urdf_reference + self.delta_radians(controller_count)

    def delta_radians(self, controller_count: int) -> float:
        return (
            self.direction
            * (controller_count - self.controller_reference)
            * self.radians_per_count
        )


# The URDF's shoulder/forearm centerlines run along local -Y and both arm joints
# rotate about +X.  At shoulder=-pi/2 and elbow=0 the two 0.22 m link vectors are
# collinear along world +Z.  With pitch=0, PyBullet places both finger joints
# above the wrist, so the claw/tool points along world +Z as physically observed.
VERTICAL_STRAIGHT_URDF = {
    "shoulder_joint": -math.pi / 2.0,
    "elbow_joint": 0.0,
    "pitch_joint": 0.0,
}


SHOULDER_CALIBRATION = JointCalibration(
    joint_name="shoulder_joint",
    controller_reference=1088,
    urdf_reference=VERTICAL_STRAIGHT_URDF["shoulder_joint"],
    counts_per_degree=33.2121,
    direction=1,
    reference_evidence=CalibrationEvidence.PHYSICALLY_ANCHORED,
    direction_evidence=CalibrationEvidence.PHYSICALLY_VERIFIED,
    scale_evidence=CalibrationEvidence.INHERITED_CONTROLLER_CONVERSION,
    note=(
        "Reference is Bingo's measured vertical-straight pose; direction follows "
        "the latest supervised physical comparison after the prior sign was reversed."
    ),
)

ELBOW_CALIBRATION = JointCalibration(
    joint_name="elbow_joint",
    controller_reference=2113,
    urdf_reference=VERTICAL_STRAIGHT_URDF["elbow_joint"],
    counts_per_degree=33.2121,
    direction=-1,
    reference_evidence=CalibrationEvidence.PHYSICALLY_ANCHORED,
    direction_evidence=CalibrationEvidence.PHYSICALLY_VERIFIED,
    scale_evidence=CalibrationEvidence.INHERITED_CONTROLLER_CONVERSION,
    note=(
        "Reference is Bingo's measured straight elbow; decreasing controller "
        "counts move toward the observed physical maximum."
    ),
)

PITCH_CALIBRATION = JointCalibration(
    joint_name="pitch_joint",
    controller_reference=1151,
    urdf_reference=VERTICAL_STRAIGHT_URDF["pitch_joint"],
    counts_per_degree=8.3555,
    direction=-1,
    reference_evidence=CalibrationEvidence.PHYSICALLY_ANCHORED,
    direction_evidence=CalibrationEvidence.PHYSICALLY_VERIFIED,
    scale_evidence=CalibrationEvidence.INHERITED_CONTROLLER_CONVERSION,
    note=(
        "Reference is the measured claw-up pose. Direction retains the prior "
        "supervised physical correction; it was not re-measured at this reference."
    ),
)

# No observation in the vertical-straight measurement constrains yaw.  This
# preserves the useful historical display (controller count zero -> URDF zero)
# while labeling that absolute reference explicitly unverified.
BASE_CALIBRATION = JointCalibration(
    joint_name="base_joint",
    controller_reference=0,
    urdf_reference=0.0,
    counts_per_degree=42.5666,
    direction=1,
    reference_evidence=CalibrationEvidence.UNVERIFIED,
    direction_evidence=CalibrationEvidence.UNVERIFIED,
    scale_evidence=CalibrationEvidence.INHERITED_CONTROLLER_CONVERSION,
    note="Legacy absolute-yaw assumption retained for utility; needs a visible yaw reference.",
)


def map_arm_controller_coordinates(
    shoulder_count: int, elbow_count: int, pitch_count: int
) -> dict[str, float]:
    """Convert the ER-V's independent link coordinates to serial URDF joints.

    Bingo mechanically/controller-maintains the forearm orientation independently
    of the upper arm: moving only the shoulder leaves the forearm pointing in its
    prior world direction.  The URDF is a conventional serial chain, so its elbow
    coordinate is relative to the upper arm and must subtract the shoulder delta.

    Pitch remains a direct reference-relative mapping until an equivalent
    forearm/pitch independence observation is physically recorded.
    """

    shoulder_delta = SHOULDER_CALIBRATION.delta_radians(shoulder_count)
    elbow_delta = ELBOW_CALIBRATION.delta_radians(elbow_count)
    return {
        SHOULDER_CALIBRATION.joint_name: (
            SHOULDER_CALIBRATION.urdf_reference + shoulder_delta
        ),
        ELBOW_CALIBRATION.joint_name: (
            ELBOW_CALIBRATION.urdf_reference + elbow_delta - shoulder_delta
        ),
        PITCH_CALIBRATION.joint_name: PITCH_CALIBRATION.to_urdf(pitch_count),
    }


def coordinated_move_counts_for_urdf_degree_deltas(
    shoulder_degrees: float, elbow_degrees: float, pitch_degrees: float
) -> tuple[int, int, int]:
    """Convert displayed ER-V joint-angle deltas into controller coordinates.

    The controller maintains forearm orientation independently of the shoulder,
    while the URDF is a serial chain.  Therefore an elbow-joint delta in the
    displayed/URDF frame includes the shoulder delta when converted back to the
    controller's independent elbow coordinate.  This is the inverse of
    :func:`map_arm_controller_coordinates` and deliberately leaves limit
    enforcement to the existing bounded coordinated-move operation.
    """
    shoulder_delta = math.radians(shoulder_degrees)
    elbow_delta = math.radians(elbow_degrees)
    pitch_delta = math.radians(pitch_degrees)
    shoulder_counts = round(
        shoulder_delta
        / (SHOULDER_CALIBRATION.direction * SHOULDER_CALIBRATION.radians_per_count)
    )
    elbow_counts = round(
        (elbow_delta + shoulder_delta)
        / (ELBOW_CALIBRATION.direction * ELBOW_CALIBRATION.radians_per_count)
    )
    pitch_counts = round(
        pitch_delta
        / (PITCH_CALIBRATION.direction * PITCH_CALIBRATION.radians_per_count)
    )
    return shoulder_counts, elbow_counts, pitch_counts
