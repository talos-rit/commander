"""Persist manually observed ER-V joint-coordinate soft endpoints.

This module deliberately records a human-supervised observation; it never issues
motion or tries to discover a mechanical stop automatically.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


_FRAME_NAMES = {
    5: ("base", "shoulder", "elbow", "pitch", "roll"),
    4: ("shoulder", "elbow", "pitch", "roll"),
}


def capture_soft_endpoint(
    destination: Path,
    *,
    robot_id: str,
    joint_counts: tuple[int, ...],
    axis: str,
    bound: str,
) -> Path:
    """Store one observed controller-coordinate endpoint.

    ``bound`` is a human label (``min`` or ``max``), not an assertion about a
    controller or mechanical hard limit.
    """
    if bound not in {"min", "max"}:
        raise ValueError("bound must be 'min' or 'max'")
    names = _FRAME_NAMES.get(len(joint_counts))
    if names is None or axis not in names:
        raise ValueError(f"{axis!r} is unavailable in this TELP frame")
    coordinate = dict(zip(names, joint_counts))[axis]
    if destination.exists():
        document = json.loads(destination.read_text(encoding="utf-8"))
    else:
        document = {
            "schema_version": 1,
            "robot_id": robot_id,
            "coordinate_source": "Operator TELP / controller LISTPV POSITION",
            "limits": {},
        }
    if document.get("robot_id") != robot_id:
        raise ValueError(f"calibration file belongs to {document.get('robot_id')!r}")
    limits = document.setdefault("limits", {})
    limits.setdefault(axis, {})[bound] = {
        "controller_count": coordinate,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "human-supervised soft endpoint",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination
