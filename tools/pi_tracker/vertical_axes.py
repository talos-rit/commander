"""Choose the vertical tracking axis. The order is fixed: elbow, shoulder, polar up/down."""

from __future__ import annotations

from typing import Optional, Tuple

Limits = Optional[Tuple[int, int]]
Motion = Optional[tuple]


def select_vertical_motion(
    *,
    elbow: bool,
    shoulder: bool,
    polar_vertical: bool,
    image_up: bool,
    elbow_count: Optional[int],
    shoulder_count: Optional[int],
    pitch_count: Optional[int],
    counts_fresh: bool,
    elbow_limits: Limits,
    shoulder_limits: Limits,
    pitch_limits: Limits,
) -> Motion:
    """Return the first enabled axis that can still move, or None to hold.

    Image-up uses the manual-jog signs: elbow negative, shoulder positive, polar altitude positive.
    A disabled axis is not a candidate. Stale or missing counts are not a stop, so a jog keeps
    commanding the current axis instead of falling through while telemetry is quiet.
    """
    altitude = 1 if image_up else -1
    candidates = []
    if elbow:
        candidates.append(("joint", 3, -altitude, elbow_count, elbow_limits))
    if shoulder:
        candidates.append(("joint", 2, altitude, shoulder_count, shoulder_limits))
    if polar_vertical:
        candidates.append(("polar", 0, altitude, pitch_count, pitch_limits))
    for kind, axis, direction, count, limits in candidates:
        if _at_count_limit(direction, count, limits, counts_fresh):
            continue
        if kind == "joint":
            return ("joint", axis, direction)
        return ("polar", direction)
    return None


def _at_count_limit(direction: int, count: Optional[int], limits: Limits, fresh: bool) -> bool:
    if not fresh or limits is None or count is None:
        return False
    low, high = limits
    if direction > 0:
        return count >= high
    if direction < 0:
        return count <= low
    return False
