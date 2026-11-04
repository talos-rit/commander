import numpy as np
import pytest

from src.observations.types import PersonObservation
from src.tracking.identity import PROVISIONAL_S, IdentityResolver, crop_is_clean


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def person(track_id, box, camera="a"):
    return PersonObservation(camera, 0, 0.0, box, 0.9, track_id)


def subject_ids(observations):
    return [o.subject_id for o in observations]


LEFT = (100, 100, 150, 250)
RIGHT = (500, 100, 550, 250)


def test_new_tracks_get_new_subject_ids_and_keep_them():
    ids = IdentityResolver(clock=Clock())

    assert subject_ids(ids.resolve("a", [person(7, LEFT), person(3, RIGHT)])) == [1, 2]
    assert subject_ids(ids.resolve("a", [person(3, RIGHT), person(7, LEFT)])) == [2, 1]


def test_tracker_fields_are_kept():
    (resolved,) = IdentityResolver(clock=Clock()).resolve("a", [person(7, LEFT)])

    assert resolved.local_track_id == 7
    assert resolved.bounding_box == LEFT


def test_untracked_detections_get_no_subject_id():
    ids = IdentityResolver(clock=Clock())

    assert subject_ids(ids.resolve("a", [person(None, LEFT)])) == [None]
    assert ids.status() == {"known": 0, "appearance": False, "faces": False, "leniency": 0.5}


def test_a_new_track_where_a_subject_was_just_lost_rejoins_it():
    clock = Clock()
    ids = IdentityResolver(clock=clock)
    ids.resolve("a", [person(7, LEFT)])

    clock.now = 0.5
    assert subject_ids(ids.resolve("a", [person(9, (110, 100, 160, 250))])) == [1]


def test_a_new_track_far_away_is_a_new_subject():
    clock = Clock()
    ids = IdentityResolver(clock=clock)
    ids.resolve("a", [person(7, LEFT)])

    clock.now = 0.5
    assert subject_ids(ids.resolve("a", [person(9, RIGHT)])) == [2]


def test_rejoining_expires():
    clock = Clock()
    ids = IdentityResolver(rejoin_s=2.0, clock=clock)
    ids.resolve("a", [person(7, LEFT)])

    clock.now = 3.0
    assert subject_ids(ids.resolve("a", [person(9, LEFT)])) == [2]
    assert ids.is_known(1)


def test_a_visible_subject_is_not_taken_by_a_new_track():
    clock = Clock()
    ids = IdentityResolver(clock=clock)
    ids.resolve("a", [person(7, LEFT)])

    clock.now = 0.1
    assert subject_ids(ids.resolve("a", [person(7, LEFT), person(9, LEFT)])) == [1, 2]


def test_each_lost_subject_rejoins_its_closest_new_track():
    clock = Clock()
    ids = IdentityResolver(clock=clock)
    ids.resolve("a", [person(1, LEFT), person(2, (200, 100, 250, 250))])

    clock.now = 0.2
    resolved = ids.resolve("a", [person(4, (190, 100, 240, 250)), person(5, (105, 100, 155, 250))])

    assert subject_ids(resolved) == [2, 1]


def test_a_subject_does_not_rejoin_on_another_camera_and_ids_do_not_collide():
    clock = Clock()
    ids = IdentityResolver(clock=clock)
    ids.resolve("a", [person(7, LEFT)])

    clock.now = 0.5
    assert subject_ids(ids.resolve("b", [person(7, LEFT, camera="b")])) == [2]


def test_a_returning_tracker_id_keeps_its_subject():
    clock = Clock()
    ids = IdentityResolver(clock=clock)
    ids.resolve("a", [person(7, LEFT)])

    clock.now = 10.0
    assert subject_ids(ids.resolve("a", [person(7, RIGHT)])) == [1]


def test_forget_all_drops_subjects_without_reusing_ids():
    ids = IdentityResolver(clock=Clock())
    ids.resolve("a", [person(7, LEFT)])

    ids.forget_all()

    assert not ids.is_known(1)
    assert ids.status() == {"known": 0, "appearance": False, "faces": False, "leniency": 0.5}
    assert subject_ids(ids.resolve("a", [person(7, LEFT)])) == [2]


# --- appearance ---------------------------------------------------------------


IMAGE = np.zeros((480, 640, 3), np.uint8)
BACKGROUND = np.ones(4, np.float32)


def look(*direction):
    """An embedding the fake model gives one outfit: the background plus a direction."""
    return BACKGROUND + np.asarray(direction, np.float32)


RED = look(1, 0, 0, 0)
RED_IN_OTHER_LIGHT = look(0.95, 0.15, 0, 0)
BLUE = look(0, 1, 0, 0)
GREEN = look(0, 0, 1, 0)


class FakeEmbedder:
    """Embeds boxes it was told about as their look, anything else as background."""

    def __init__(self):
        self.looks: dict[tuple, np.ndarray] = {}
        self.calls = 0

    def wear(self, box, vector):
        self.looks[tuple(box)] = vector
        return box

    def embed(self, image, boxes):
        self.calls += 1
        return [self.looks.get(tuple(box), BACKGROUND).copy() for box in boxes]


def appearance(clock):
    embedder = FakeEmbedder()
    return IdentityResolver(embedder=embedder, clock=clock, rng=np.random.default_rng(0)), embedder


def test_someone_who_comes_back_later_is_recognized():
    clock = Clock()
    ids, looks = appearance(clock)
    ids.resolve("a", [person(1, looks.wear(LEFT, RED))], IMAGE)
    ids.resolve("a", [], IMAGE)

    clock.now = 60.0
    back = looks.wear((300, 120, 350, 270), RED_IN_OTHER_LIGHT)
    assert subject_ids(ids.resolve("a", [person(14, back)], IMAGE)) == [1]
    assert ids.status() == {"known": 1, "appearance": True, "faces": False, "leniency": 0.5}


def test_someone_who_looks_different_is_a_new_subject():
    clock = Clock()
    ids, looks = appearance(clock)
    ids.resolve("a", [person(1, looks.wear(LEFT, RED))], IMAGE)

    clock.now = 60.0
    assert subject_ids(ids.resolve("a", [person(2, looks.wear(RIGHT, BLUE))], IMAGE)) == [2]


def test_people_who_come_back_together_each_get_their_own_id():
    clock = Clock()
    ids, looks = appearance(clock)
    ids.resolve("a", [person(1, looks.wear(LEFT, RED)), person(2, looks.wear(RIGHT, BLUE))], IMAGE)

    clock.now = 60.0
    looks.looks.clear()
    back = [person(8, looks.wear(LEFT, BLUE)), person(9, looks.wear(RIGHT, RED))]
    assert subject_ids(ids.resolve("a", back, IMAGE)) == [2, 1]


def test_a_visible_subject_is_not_given_to_a_lookalike():
    clock = Clock()
    ids, looks = appearance(clock)
    ids.resolve("a", [person(1, looks.wear(LEFT, RED))], IMAGE)

    clock.now = 5.0
    twin = looks.wear(RIGHT, RED)
    assert subject_ids(ids.resolve("a", [person(1, LEFT), person(2, twin)], IMAGE)) == [1, 2]


def test_someone_cut_off_by_the_edge_is_recognized_once_fully_in_view():
    clock = Clock()
    ids, looks = appearance(clock)
    ids.resolve("a", [person(1, looks.wear(LEFT, RED))], IMAGE)

    clock.now = 60.0
    entering = looks.wear((0, 100, 40, 250), RED)
    assert subject_ids(ids.resolve("a", [person(5, entering)], IMAGE)) == [2]
    assert ids.is_known(2)

    clock.now = 61.0
    assert subject_ids(ids.resolve("a", [person(5, looks.wear(LEFT, RED))], IMAGE)) == [1]
    assert ids.canonical(2) == 1
    assert ids.is_known(2)
    assert ids.status()["known"] == 1


def test_a_new_subject_is_final_after_the_provisional_window():
    clock = Clock()
    ids, looks = appearance(clock)
    ids.resolve("a", [person(1, looks.wear(LEFT, RED))], IMAGE)

    clock.now = 60.0
    entering = looks.wear((0, 100, 40, 250), RED)
    ids.resolve("a", [person(5, entering)], IMAGE)

    clock.now = 60.0 + PROVISIONAL_S + 0.1
    assert subject_ids(ids.resolve("a", [person(5, looks.wear(LEFT, RED))], IMAGE)) == [2]


def test_a_look_the_tracker_swapped_in_is_not_learned():
    clock = Clock()
    ids, looks = appearance(clock)
    ids.resolve("a", [person(1, looks.wear(LEFT, RED))], IMAGE)

    clock.now = 5.0  # same tracker ID, but now on someone in green
    looks.looks.clear()
    ids.resolve("a", [person(1, looks.wear(LEFT, GREEN))], IMAGE)

    clock.now = 60.0
    assert subject_ids(ids.resolve("a", [person(2, looks.wear(RIGHT, GREEN))], IMAGE)) == [2]


def test_a_gradually_changing_look_is_learned():
    clock = Clock()
    ids, looks = appearance(clock)
    ids.resolve("a", [person(1, looks.wear(LEFT, look(1, 0, 0, 0)))], IMAGE)
    clock.now = 2.0
    ids.resolve("a", [person(1, looks.wear(LEFT, look(0.7, 0.7, 0, 0)))], IMAGE)
    clock.now = 4.0
    ids.resolve("a", [person(1, looks.wear(LEFT, look(0, 1, 0, 0)))], IMAGE)

    clock.now = 60.0
    assert subject_ids(ids.resolve("a", [person(2, looks.wear(RIGHT, look(0, 1, 0, 0)))], IMAGE)) == [1]


def test_without_a_frame_or_a_ready_model_only_position_is_used():
    clock = Clock()
    ids, looks = appearance(clock)
    ids.resolve("a", [person(1, looks.wear(LEFT, RED))])

    clock.now = 60.0
    assert subject_ids(ids.resolve("a", [person(2, looks.wear(RIGHT, RED))])) == [2]
    assert looks.calls == 0

    not_ready = IdentityResolver(embedder=type("NotReady", (), {"embed": lambda *_: []})(), clock=clock)
    assert subject_ids(not_ready.resolve("a", [person(1, LEFT)], IMAGE)) == [1]
    assert not_ready.status()["appearance"] is False


def test_crops_are_embedded_only_when_clean():
    def clean(*observations):
        return [crop_is_clean(list(observations), i, 640) for i in range(len(observations))]

    assert clean(person(1, LEFT)) == [True]
    assert clean(PersonObservation("a", 0, 0.0, LEFT, 0.3, 1)) == [False]
    assert clean(person(1, (100, 100, 150, 140))) == [False]  # too small
    assert clean(person(1, (0, 100, 50, 250)), person(2, (600, 100, 640, 250))) == [False, False]
    assert clean(person(1, (100, 0, 150, 480))) == [True]  # cut off top and bottom is fine
    assert clean(person(1, LEFT), person(2, (130, 100, 180, 250))) == [False, False]


# --- faces --------------------------------------------------------------------

ALICE = np.array([1, 0, 0, 0], np.float32)
ALICE_TURNED = np.array([0.8, 0.6, 0, 0], np.float32)
BOB = np.array([0, 0, 1, 0], np.float32)


class FakeFaces:
    """Shows the face it was told about for a box, and no face anywhere else."""

    def __init__(self):
        self.faces: dict[tuple, np.ndarray] = {}

    def show(self, box, face):
        self.faces[tuple(box)] = face
        return box

    def embed(self, image, boxes):
        return [self.faces.get(tuple(box)) for box in boxes]


def with_faces(clock):
    bodies, faces = FakeEmbedder(), FakeFaces()
    ids = IdentityResolver(embedder=bodies, face_embedder=faces, clock=clock, rng=np.random.default_rng(0))
    return ids, bodies, faces


def test_a_face_recognizes_someone_who_changed_clothes():
    clock = Clock()
    ids, bodies, faces = with_faces(clock)
    ids.resolve("a", [person(1, faces.show(bodies.wear(LEFT, RED), ALICE))], IMAGE)

    clock.now = 60.0
    back = faces.show(bodies.wear(RIGHT, GREEN), ALICE_TURNED)
    assert subject_ids(ids.resolve("a", [person(2, back)], IMAGE)) == [1]


def test_different_faces_keep_lookalikes_apart():
    clock = Clock()
    ids, bodies, faces = with_faces(clock)
    ids.resolve("a", [person(1, faces.show(bodies.wear(LEFT, RED), ALICE))], IMAGE)

    clock.now = 60.0
    twin = faces.show(bodies.wear(RIGHT, RED), BOB)
    assert subject_ids(ids.resolve("a", [person(2, twin)], IMAGE)) == [2]


def test_body_decides_when_no_face_shows():
    clock = Clock()
    ids, bodies, faces = with_faces(clock)
    ids.resolve("a", [person(1, faces.show(bodies.wear(LEFT, RED), ALICE))], IMAGE)

    clock.now = 60.0
    facing_away = bodies.wear(RIGHT, RED)
    assert subject_ids(ids.resolve("a", [person(2, facing_away)], IMAGE)) == [1]


def test_a_face_outranks_a_closer_body_match():
    clock = Clock()
    ids, bodies, faces = with_faces(clock)
    ids.resolve(
        "a",
        [
            person(1, faces.show(bodies.wear(LEFT, RED), ALICE)),
            person(2, faces.show(bodies.wear(RIGHT, BLUE), BOB)),
        ],
        IMAGE,
    )

    clock.now = 60.0  # Bob borrowed Alice's red jacket
    back = faces.show(bodies.wear((300, 120, 350, 270), RED), BOB)
    assert subject_ids(ids.resolve("a", [person(3, back)], IMAGE)) == [2]


def test_a_settled_subject_is_merged_when_their_face_finally_shows():
    clock = Clock()
    ids, bodies, faces = with_faces(clock)
    ids.resolve("a", [person(1, faces.show(bodies.wear(LEFT, RED), ALICE))], IMAGE)

    clock.now = 60.0  # back in new clothes, facing away
    assert subject_ids(ids.resolve("a", [person(2, bodies.wear(RIGHT, GREEN))], IMAGE)) == [2]

    clock.now = 60.0 + PROVISIONAL_S + 1.0  # settled, then turns around
    faces.show(RIGHT, ALICE_TURNED)
    assert subject_ids(ids.resolve("a", [person(2, RIGHT)], IMAGE)) == [1]
    assert ids.canonical(2) == 1


def test_a_face_the_tracker_swapped_in_is_not_learned():
    clock = Clock()
    ids, bodies, faces = with_faces(clock)
    ids.resolve("a", [person(1, faces.show(bodies.wear(LEFT, RED), ALICE))], IMAGE)

    clock.now = 5.0  # same tracker ID, now on Bob, dressed alike
    faces.faces.clear()
    ids.resolve("a", [person(1, faces.show(LEFT, BOB))], IMAGE)

    clock.now = 60.0
    assert subject_ids(ids.resolve("a", [person(2, faces.show(RIGHT, BOB))], IMAGE)) == [2]


def test_faces_work_without_a_body_model():
    clock = Clock()
    faces = FakeFaces()
    ids = IdentityResolver(face_embedder=faces, clock=clock)
    ids.resolve("a", [person(1, faces.show(LEFT, ALICE))], IMAGE)

    clock.now = 60.0
    assert subject_ids(ids.resolve("a", [person(2, faces.show(RIGHT, ALICE))], IMAGE)) == [1]
    assert ids.status() == {"known": 1, "appearance": False, "faces": True, "leniency": 0.5}


def test_faces_are_matched_even_when_people_stand_close():
    clock = Clock()
    ids, bodies, faces = with_faces(clock)
    close = [faces.show(LEFT, ALICE), faces.show((120, 100, 170, 250), BOB)]
    ids.resolve("a", [person(1, close[0]), person(2, close[1])], IMAGE)

    clock.now = 60.0
    assert subject_ids(ids.resolve("a", [person(5, close[1]), person(6, close[0])], IMAGE)) == [2, 1]


# --- leniency -------------------------------------------------------------------


def test_leniency_moves_both_thresholds_and_is_validated():
    ids = IdentityResolver(clock=Clock())
    assert (ids.match_threshold, ids.face_match_threshold) == pytest.approx((0.85, 0.363))

    ids.set_leniency(0.0)
    strict = (ids.match_threshold, ids.face_match_threshold)
    ids.set_leniency(1.0)

    assert ids.match_threshold < strict[0] and ids.face_match_threshold < strict[1]
    with pytest.raises(ValueError):
        ids.set_leniency(-0.1)


def test_strict_turns_away_a_match_lenient_accepts():
    def returning(leniency):
        clock = Clock()
        ids, looks = appearance(clock)
        ids.set_leniency(leniency)
        ids.resolve("a", [person(1, looks.wear(LEFT, RED))], IMAGE)
        clock.now = 60.0
        changed = looks.wear(RIGHT, look(0.9, 0.5, 0, 0))  # about 0.87 alike
        return subject_ids(ids.resolve("a", [person(2, changed)], IMAGE))

    assert returning(0.0) == [2]
    assert returning(1.0) == [1]


def test_last_match_reports_how_a_subject_was_recognized():
    clock = Clock()
    ids, bodies, faces = with_faces(clock)
    ids.resolve("a", [person(1, faces.show(bodies.wear(LEFT, RED), ALICE))], IMAGE)
    assert ids.last_match(1) is None

    clock.now = 60.0
    ids.resolve("a", [person(2, faces.show(bodies.wear(RIGHT, GREEN), ALICE))], IMAGE)

    assert ids.last_match(1) == {"by": "face", "score": 1.0}
    assert ids.last_match(99) is None
