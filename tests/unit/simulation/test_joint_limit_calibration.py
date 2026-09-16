import json

import pytest

from src.simulation.joint_limit_calibration import capture_soft_endpoint


def test_capture_preserves_manual_endpoint_evidence(tmp_path):
    destination = tmp_path / "bluey_joint_limits.local.json"

    capture_soft_endpoint(
        destination,
        robot_id="bluey",
        joint_counts=(10, 20, 30, 40, 50),
        axis="elbow",
        bound="max",
    )
    capture_soft_endpoint(
        destination,
        robot_id="bluey",
        joint_counts=(11, 21, 31, 41, 51),
        axis="elbow",
        bound="min",
    )

    document = json.loads(destination.read_text(encoding="utf-8"))
    assert document["coordinate_source"] == "Operator TELP / controller LISTPV POSITION"
    assert document["limits"]["elbow"]["max"]["controller_count"] == 30
    assert document["limits"]["elbow"]["min"]["controller_count"] == 31
    assert document["limits"]["elbow"]["max"]["kind"] == "human-supervised soft endpoint"


def test_capture_rejects_base_when_legacy_telp_has_no_base(tmp_path):
    with pytest.raises(ValueError, match="unavailable"):
        capture_soft_endpoint(
            tmp_path / "limits.json",
            robot_id="bluey",
            joint_counts=(20, 30, 40, 50),
            axis="base",
            bound="min",
        )
