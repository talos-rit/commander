import numpy as np
import pytest

import src.config as config_module
from src.config.schema.robot import ConnectionConfig
from src.connection.connection import Connection, ConnectionCollection
from src.observations.types import PersonObservation
from src.streaming.streamer import Streamer


class StillVideo:
    def __init__(self, frame):
        self.frame = frame

    def set_camera_id(self, _camera_id):
        pass

    def get_latest_frame(self):
        return self.frame


class NullPublisher:
    def close(self):
        pass


@pytest.fixture
def connection(monkeypatch):
    robot = ConnectionConfig(socket_host="a", socket_port=1, camera_index=0)
    monkeypatch.setattr(config_module, "ROBOT_CONFIGS", {"a": robot}, raising=False)
    frame = np.zeros((480, 640, 3), np.uint8)
    frame[200:300, 300:340] = 255
    return Connection(
        "a", 1, StillVideo(frame), publisher_factory=lambda *_: NullPublisher()
    )


def person(track_id, box):
    return PersonObservation("a", 0, 0.0, box, 0.9, track_id)


def test_tracking_bboxes_follow_only_the_focus_subject(connection):
    connection.set_observations([person(1, (0, 0, 10, 10)), person(2, (20, 20, 40, 40))])
    assert connection.get_tracking_bboxes() == [(0, 0, 10, 10), (20, 20, 40, 40)]

    connection.focus_subject_id = 2
    assert connection.get_tracking_bboxes() == [(20, 20, 40, 40)]

    connection.focus_subject_id = 9
    assert connection.get_tracking_bboxes() == []


def test_focus_survives_a_tracker_id_switch(connection):
    connection.set_observations([person(1, (300, 200, 340, 300))])
    connection.focus_subject_id = 1

    connection.set_observations([person(8, (305, 200, 345, 300))])

    assert connection.get_observations()[0].subject_id == 1
    assert connection.get_tracking_bboxes() == [(305, 200, 345, 300)]


def test_streamer_zooms_on_focus_subject(connection):
    connections = ConnectionCollection()
    connections["a"] = connection
    streamer = Streamer(connections)
    streamer.zoom("a").smoothing_s = 0
    connection.set_observations([person(4, (300, 200, 340, 300))])

    full = streamer.get_frame("a")
    connection.focus_subject_id = 1
    zoomed = streamer.get_frame("a")

    assert full.shape == zoomed.shape
    assert zoomed.mean() > full.mean()
    assert streamer.zoom("a").status()["locked"] is True


def test_streamer_labels_subjects_when_drawing(connection):
    connections = ConnectionCollection()
    connections["a"] = connection
    streamer = Streamer(connections, draw_bboxes=True)
    connection.set_observations([person(4, (300, 200, 340, 300))])

    frame = streamer.get_frame("a")

    assert frame is not connection.video_connection.frame
    assert frame.shape == (480, 640, 3)


def test_connection_hands_the_detected_frame_to_identity_and_follows_merges(connection):
    from dataclasses import replace

    from src.observations.types import FramePacket

    seen = []

    class MergingIdentity:
        def resolve(self, camera_id, observations, image=None):
            seen.append(image)
            return [replace(o, subject_id=1) for o in observations]

        def canonical(self, subject_id):
            return 1

    packet = FramePacket("a", 7, 0.0, connection.video_connection.frame)
    connection.video_connection.get_packet = lambda sequence: packet if sequence == 7 else None
    connection.identity = MergingIdentity()
    connection.focus_subject_id = 2

    connection.set_observations([PersonObservation("a", 7, 0.0, (0, 0, 10, 10), 0.9, 3)])
    connection.set_observations([PersonObservation("a", 8, 0.0, (0, 0, 10, 10), 0.9, 3)])

    assert seen == [packet.image, None]
    assert connection.focus_subject_id == 1
