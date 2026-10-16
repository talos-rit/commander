import numpy as np
import pytest

from src.observations.types import PersonObservation
from src.streaming.zoom import DigitalZoom, framing_rect

FRAME = (480, 640, 3)


def person(track_id, box):
    return PersonObservation(
        camera_id="cam",
        frame_sequence=0,
        capture_timestamp=0.0,
        bounding_box=box,
        detection_confidence=0.9,
        local_track_id=track_id,
    )


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def contains(rect, box):
    return rect[0] <= box[0] and rect[1] <= box[1] and rect[2] >= box[2] and rect[3] >= box[3]


def test_framing_keeps_frame_aspect_and_contains_subject():
    box = (300, 200, 340, 300)
    rect = framing_rect(box, 640, 480, fill=0.6)

    width, height = rect[2] - rect[0], rect[3] - rect[1]
    assert width / height == pytest.approx(640 / 480)
    assert contains(rect, box)
    # Height-limited: the subject takes up 60% of the crop's height.
    assert 100 / height == pytest.approx(0.6)


def test_framing_shifts_inside_frame_without_cutting_off_subject():
    box = (600, 400, 640, 480)  # bottom-right corner
    rect = framing_rect(box, 640, 480, fill=0.6)

    assert rect[2] == pytest.approx(640)
    assert rect[3] == pytest.approx(480)
    assert contains(rect, box)


def test_framing_respects_max_zoom_and_full_frame():
    tiny = framing_rect((320, 240, 322, 242), 640, 480, fill=0.6, max_zoom=4.0)
    assert tiny[2] - tiny[0] == pytest.approx(160)

    huge = framing_rect((0, 0, 640, 480), 640, 480, fill=0.6)
    assert huge == pytest.approx((0, 0, 640, 480))


def test_zoom_tightens_as_subject_gets_smaller():
    near = framing_rect((250, 100, 390, 460), 640, 480, fill=0.6)
    far = framing_rect((300, 200, 340, 300), 640, 480, fill=0.6)

    assert far[2] - far[0] < near[2] - near[0]


def test_zoom_eases_toward_the_subject():
    clock = Clock()
    zoom = DigitalZoom(smoothing_s=0.3, clock=clock)
    subject = [person(3, (300, 200, 340, 300))]
    zoom.update(FRAME, subject, None)  # starts at full frame

    clock.now = 0.1
    first = zoom.update(FRAME, subject, 3)
    clock.now = 2.0
    settled = zoom.update(FRAME, subject, 3)

    target = framing_rect((300, 200, 340, 300), 640, 480, fill=0.6)
    assert first[2] - first[0] > settled[2] - settled[0]
    assert settled == pytest.approx(target, abs=0.5)
    assert zoom.status()["locked"] is True
    assert zoom.status()["level"] > 1


def test_zoom_holds_when_subject_is_briefly_lost_then_returns_to_full_frame():
    clock = Clock()
    zoom = DigitalZoom(smoothing_s=0, lost_hold_s=1.0, clock=clock)
    framed = zoom.update(FRAME, [person(3, (300, 200, 340, 300))], 3)

    clock.now = 0.5
    assert zoom.update(FRAME, [], 3) == framed
    assert zoom.status()["holding"] is True

    clock.now = 2.0
    assert zoom.update(FRAME, [], 3) == (0, 0, 640, 480)
    assert zoom.status()["locked"] is False


def test_zoom_ignores_other_subjects():
    zoom = DigitalZoom(smoothing_s=0)

    rect = zoom.update(FRAME, [person(1, (10, 10, 50, 100))], 3)

    assert rect == (0, 0, 640, 480)


def test_apply_returns_frame_of_the_same_size():
    zoom = DigitalZoom(smoothing_s=0)
    frame = np.zeros(FRAME, np.uint8)
    frame[200:300, 300:340] = 255

    zoomed = zoom.apply(frame, [person(3, (300, 200, 340, 300))], 3)

    assert zoomed.shape == frame.shape
    assert zoomed.mean() > frame.mean()


def test_apply_without_target_returns_original_frame():
    frame = np.zeros(FRAME, np.uint8)

    assert DigitalZoom().apply(frame, [], None) is frame


def test_fill_is_validated():
    zoom = DigitalZoom()

    assert zoom.set_fill(0.8) == 0.8
    with pytest.raises(ValueError):
        zoom.set_fill(0.05)
