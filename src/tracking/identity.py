"""Persistent subject IDs layered over short-lived tracker IDs.

Trackers forget a person within a second or two of losing them, then hand out
a new ID. The resolver maps each (camera, tracker ID) to a subject ID that
outlives the track, so a zoom or follow target survives the person leaving.

A new track takes over a known subject in one of two ways:

- Position: the subject was lost moments ago at about the same spot, which
  covers tracker ID switches.
- Appearance: its body embedding is close to one the subject was seen with.
  This is what recognizes someone who walks back in later.

Appearance means the face when both sides have one, else the body. A clear
face match wins over any body match, and two clearly different faces rule a
match out however alike the clothes are.

A track that matches neither gets a provisional new subject, and keeps being
compared for a few seconds, since people walking in are often cut off by the
frame edge at first. If it matches then, the provisional subject is merged
into the known one. A subject whose face shows for the first time can still
be merged by that face later, since people often come back facing away.
"""

import dataclasses
import math
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np
from loguru import logger

from src.observations.types import BBox, PersonObservation
from src.tracking.embedding import Embedder, FaceEmbedder

REJOIN_S = 2.0
"""How long after losing a subject a new track may take over its ID by position."""
MAX_JUMP = 1.0
"""How far a rejoining track may be from where the subject was lost, in box sizes."""
TRACK_TTL_S = 30.0
"""How long to remember which subject a vanished tracker ID belonged to."""

MATCH_THRESHOLD = (0.95, 0.75)
"""Body similarity at which a new track is taken to be a known subject, from
strictest to most lenient. Halfway, 0.85, is the default."""
CONSISTENCY_THRESHOLD = 0.5
"""A tracked subject only learns a new look this close to how they already looked.

Lower than `MATCH_THRESHOLD` so gradual changes, like taking off a jacket in
view, are learned; high enough to skip crops where the tracker swapped people.
"""
REDUNDANT = 0.97
"""Samples this close to one already kept add nothing."""
MAX_SAMPLES = 10
PROVISIONAL_S = 3.0
"""How long a new subject keeps being compared with known ones before its ID is final."""
RECHECK_S = 0.25
"""How often a provisional subject is re-embedded."""
REFRESH_S = 1.0
"""How often a settled subject is re-embedded to learn how they look."""
MAX_EMBEDS = 4
"""Person crops embedded per frame at most, so a crowd cannot stall detection."""

FACE_MATCH_THRESHOLD = (0.443, 0.283)
"""Face similarity for the same person, strictest to most lenient. Halfway is
0.363, OpenCV's suggested SFace threshold."""
DEFAULT_LENIENCY = 0.5
FACE_REJECT_THRESHOLD = 0.2
"""Faces less alike than this are different people, whatever the clothes say."""
FACE_REDUNDANT = 0.9
MAX_FACE_EMBEDS = 2
"""Faces looked for per frame at most; each costs about as much as two body crops."""

MIN_CONFIDENCE = 0.5
MIN_BOX_PX = 64
EDGE_PX = 4
"""Boxes this close to the left or right edge are likely cut off."""
MAX_OVERLAP = 0.1
"""Share of a box that may be covered by other boxes before its crop is mixed."""

BACKGROUND_CROPS = 4
BACKGROUND_WARMUP = 32
"""Scene crops averaged before the background settles and refreshes slowly."""
BACKGROUND_WARMUP_S = 0.5
BACKGROUND_REFRESH_S = 5.0
BACKGROUND_EMA = 0.05


@dataclass(slots=True)
class _Subject:
    camera_id: str
    box: BBox
    last_seen: float
    samples: list[np.ndarray] = field(default_factory=list)
    """Raw body embeddings. Centered only when compared, since the background drifts."""
    faces: list[np.ndarray] = field(default_factory=list)
    """Unit-length face embeddings."""
    match: tuple[str, float] | None = None
    """How this subject was last recognized: "face" or "body", and the similarity."""


@dataclass(slots=True)
class _Track:
    subject_id: int
    last_seen: float
    last_embed: float = -math.inf
    provisional_until: float | None = None


def _center(box: BBox) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _size(box: BBox) -> float:
    x1, y1, x2, y2 = box
    return max(1.0, float(x2 - x1), float(y2 - y1))


def _covered(box: BBox, other: BBox) -> float:
    """Share of `box` that `other` covers."""
    width = min(box[2], other[2]) - max(box[0], other[0])
    height = min(box[3], other[3]) - max(box[1], other[1])
    if width <= 0 or height <= 0:
        return 0.0
    return width * height / max(1.0, float((box[2] - box[0]) * (box[3] - box[1])))


def _unit(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).ravel()
    return vector / max(float(np.linalg.norm(vector)), 1e-6)


def _drop_most_redundant(samples: list[np.ndarray], units: np.ndarray) -> None:
    """Remove the sample most like another, keeping the set varied."""
    similarity = units @ units.T
    np.fill_diagonal(similarity, -np.inf)
    del samples[int(np.argmax(similarity.max(axis=1)))]


def worth_a_look(observation: PersonObservation) -> bool:
    """Whether a box is confident and big enough to look for a face in."""
    box = observation.bounding_box
    confidence = observation.detection_confidence
    if confidence is not None and confidence < MIN_CONFIDENCE:
        return False
    return box[3] - box[1] >= MIN_BOX_PX


def crop_is_clean(observations: list[PersonObservation], index: int, width: int) -> bool:
    """Whether a box is also whole and unobstructed enough to embed the body.

    Faces skip these checks: a face is small, so another person's box rarely
    hides it, and someone at the edge of the frame often shows theirs.
    """
    if not worth_a_look(observations[index]):
        return False
    box = observations[index].bounding_box
    # Only the sides: a webcam crops most people at the bottom and some at the top.
    if box[0] <= EDGE_PX or box[2] >= width - EDGE_PX:
        return False
    return all(
        _covered(box, other.bounding_box) <= MAX_OVERLAP
        for other_index, other in enumerate(observations)
        if other_index != index
    )


class IdentityResolver:
    """Hands out subject IDs that persist across tracker IDs and cameras.

    One instance is shared by every camera so IDs never collide and a person
    can be recognized on either. Safe to call from several detection threads
    at once. Without embedders, or without frames, only position is used.
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        face_embedder: FaceEmbedder | None = None,
        leniency: float = DEFAULT_LENIENCY,
        consistency_threshold: float = CONSISTENCY_THRESHOLD,
        provisional_s: float = PROVISIONAL_S,
        rejoin_s: float = REJOIN_S,
        max_jump: float = MAX_JUMP,
        track_ttl_s: float = TRACK_TTL_S,
        clock: Callable[[], float] = time.monotonic,
        rng: np.random.Generator | None = None,
    ):
        self.embedder = embedder
        self.face_embedder = face_embedder
        self.set_leniency(leniency)
        self.consistency_threshold = consistency_threshold
        self.provisional_s = provisional_s
        self.rejoin_s = rejoin_s
        self.max_jump = max_jump
        self.track_ttl_s = track_ttl_s
        self.clock = clock
        self._rng = rng or np.random.default_rng()
        self._lock = threading.Lock()
        self._subjects: dict[int, _Subject] = {}
        self._tracks: dict[tuple[str, int], _Track] = {}
        self._aliases: dict[int, int] = {}
        """Merged provisional subject -> the subject it turned out to be."""
        self._next = 1
        self._background: np.ndarray | None = None
        """Mean embedding of random scene crops, subtracted before comparing.

        Classifier features are all positive, so raw cosine similarity sits
        near 1 for any two crops; centering spreads it out.
        """
        self._background_count = 0
        self._background_at = -math.inf

    def resolve(
        self,
        camera_id: str,
        observations: Iterable[PersonObservation],
        image: np.ndarray | None = None,
    ) -> list[PersonObservation]:
        """Return `observations`, one camera frame's worth, with `subject_id` set.

        `image` is the frame the boxes were detected on, for appearance
        matching. Detections without a tracker ID get no subject ID.
        """
        observations = list(observations)
        now = self.clock()
        with self._lock:
            self._tracks = {
                key: track
                for key, track in self._tracks.items()
                if now - track.last_seen <= self.track_ttl_s
            }
            ids: list[int | None] = [None] * len(observations)
            tracks: list[_Track | None] = [None] * len(observations)
            taken: set[int] = set()
            new: list[int] = []
            for index, observation in enumerate(observations):
                if observation.local_track_id is None:
                    continue
                track = self._tracks.get((camera_id, observation.local_track_id))
                subject_id = self._canonical(track.subject_id) if track else None
                if subject_id in self._subjects and subject_id not in taken:
                    ids[index], tracks[index] = subject_id, track
                    taken.add(subject_id)
                else:
                    new.append(index)

            for index, subject_id in self._rejoin(camera_id, observations, new, taken, now):
                ids[index] = subject_id
                taken.add(subject_id)
            unmatched = [index for index in new if ids[index] is None]
            vectors, faces = self._embed(observations, image, unmatched, tracks, now)
            for index, subject_id in self._match(unmatched, vectors, faces, taken):
                ids[index] = subject_id
                taken.add(subject_id)
            provisional = set()
            for index in unmatched:
                if ids[index] is None:
                    ids[index], self._next = self._next, self._next + 1
                    provisional.add(index)
            self._recheck(tracks, ids, vectors, faces, taken, now)

            resolved = []
            for index, observation in enumerate(observations):
                subject_id = ids[index]
                if subject_id is not None and observation.local_track_id is not None:
                    self._record(
                        camera_id, observation, subject_id, tracks[index],
                        index in provisional, vectors.get(index), faces.get(index), now,
                    )
                resolved.append(dataclasses.replace(observation, subject_id=subject_id))
            return resolved

    def _record(
        self,
        camera_id: str,
        observation: PersonObservation,
        subject_id: int,
        track: _Track | None,
        provisional: bool,
        vector: np.ndarray | None,
        face: np.ndarray | None,
        now: float,
    ) -> None:
        if track is None:
            track = _Track(subject_id, now)
            if provisional:
                track.provisional_until = now + self.provisional_s
            assert observation.local_track_id is not None
            self._tracks[(camera_id, observation.local_track_id)] = track
        track.subject_id = subject_id
        track.last_seen = now
        subject = self._subjects.get(subject_id)
        if subject is None:
            subject = self._subjects[subject_id] = _Subject(camera_id, observation.bounding_box, now)
        subject.camera_id, subject.box, subject.last_seen = camera_id, observation.bounding_box, now
        if vector is not None or face is not None:
            track.last_embed = now
            self._enroll(subject, vector, face)

    def _rejoin(
        self,
        camera_id: str,
        observations: list[PersonObservation],
        new: list[int],
        taken: set[int],
        now: float,
    ) -> list[tuple[int, int]]:
        """Pair new tracks with subjects just lost nearby, closest pairs first."""
        lost = {
            subject_id: subject
            for subject_id, subject in self._subjects.items()
            if subject_id not in taken
            and subject.camera_id == camera_id
            and now - subject.last_seen <= self.rejoin_s
        }
        pairs = sorted(
            (
                math.dist(_center(observations[index].bounding_box), _center(subject.box))
                / _size(subject.box),
                index,
                subject_id,
            )
            for index in new
            for subject_id, subject in lost.items()
        )
        matched: list[tuple[int, int]] = []
        used_tracks: set[int] = set()
        used_subjects: set[int] = set()
        for jump, index, subject_id in pairs:
            if jump > self.max_jump:
                break
            if index not in used_tracks and subject_id not in used_subjects:
                matched.append((index, subject_id))
                used_tracks.add(index)
                used_subjects.add(subject_id)
        return matched

    def _embed(
        self,
        observations: list[PersonObservation],
        image: np.ndarray | None,
        unmatched: list[int],
        tracks: list[_Track | None],
        now: float,
    ) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
        """Body and face embeddings, by index, for the crops that need them most."""
        if image is None or (self.embedder is None and self.face_embedder is None):
            return {}, {}
        height, width = image.shape[:2]
        if self.embedder is not None:
            self._update_background(image, width, height, now)
        due_provisional = [
            index
            for index, track in enumerate(tracks)
            if track is not None
            and track.provisional_until is not None
            and now - track.last_embed >= RECHECK_S
        ]
        due_refresh = [
            index
            for index, track in enumerate(tracks)
            if track is not None
            and track.provisional_until is None
            and now - track.last_embed >= REFRESH_S
        ]
        due = unmatched + due_provisional + due_refresh
        bodies = [i for i in due if crop_is_clean(observations, i, width)][:MAX_EMBEDS]
        heads = [i for i in due if worth_a_look(observations[i])][:MAX_FACE_EMBEDS]
        for index in {*bodies, *heads}:
            if (track := tracks[index]) is not None:
                track.last_embed = now  # also when no face shows, so it is not retried every frame
        vectors: dict[int, np.ndarray] = {}
        faces: dict[int, np.ndarray] = {}
        if bodies and self.embedder is not None and self._background is not None:
            found = self.embedder.embed(image, [observations[i].bounding_box for i in bodies])
            if len(found) == len(bodies):
                vectors = dict(zip(bodies, found))
        if heads and self.face_embedder is not None:
            found_faces = self.face_embedder.embed(image, [observations[i].bounding_box for i in heads])
            if len(found_faces) == len(heads):
                faces = {i: _unit(face) for i, face in zip(heads, found_faces) if face is not None}
        return vectors, faces

    def _update_background(self, image: np.ndarray, width: int, height: int, now: float) -> None:
        interval = (
            BACKGROUND_WARMUP_S if self._background_count < BACKGROUND_WARMUP else BACKGROUND_REFRESH_S
        )
        if now - self._background_at < interval:
            return
        assert self.embedder is not None
        boxes = []
        for _ in range(BACKGROUND_CROPS):
            box_height = self._rng.uniform(0.3, 0.8) * height
            box_width = min(width, box_height * self._rng.uniform(0.3, 0.5))
            x = self._rng.uniform(0, width - box_width)
            y = self._rng.uniform(0, height - box_height)
            boxes.append((x, y, x + box_width, y + box_height))
        vectors = self.embedder.embed(image, boxes)
        if len(vectors) != len(boxes):
            return
        self._background_at = now
        mean = np.mean(vectors, axis=0)
        if self._background is None:
            self._background = mean
        elif self._background_count < BACKGROUND_WARMUP:
            weight = len(vectors) / (self._background_count + len(vectors))
            self._background = self._background + (mean - self._background) * weight
        else:
            self._background = self._background + (mean - self._background) * BACKGROUND_EMA
        self._background_count += len(vectors)

    def _centered(self, vectors: list[np.ndarray] | np.ndarray) -> np.ndarray:
        assert self._background is not None
        centered = np.asarray(vectors, dtype=np.float32) - self._background
        norms = np.linalg.norm(centered, axis=-1, keepdims=True)
        return centered / np.maximum(norms, 1e-6)

    def _similarity(self, vector: np.ndarray, subject: _Subject) -> float:
        if not subject.samples or self._background is None:
            return -1.0
        return float(np.max(self._centered(subject.samples) @ self._centered(vector)))

    def _score(
        self,
        index: int,
        subject: _Subject,
        vectors: dict[int, np.ndarray],
        faces: dict[int, np.ndarray],
    ) -> float | None:
        """How strongly a track looks like a subject, or None if it does not.

        A face match scores above 1 so it outranks any body match.
        """
        face = faces.get(index)
        if face is not None and subject.faces:
            similarity = float(np.max(np.stack(subject.faces) @ face))
            if similarity >= self.face_match_threshold:
                return 1.0 + similarity
            if similarity < FACE_REJECT_THRESHOLD:
                return None
        vector = vectors.get(index)
        if vector is None:
            return None
        similarity = self._similarity(vector, subject)
        return similarity if similarity >= self.match_threshold else None

    def _match(
        self,
        indices: list[int],
        vectors: dict[int, np.ndarray],
        faces: dict[int, np.ndarray],
        taken: set[int],
    ) -> list[tuple[int, int]]:
        """Pair tracks with known subjects by appearance, strongest first."""
        scored = (
            (self._score(index, subject, vectors, faces), index, subject_id)
            for index in indices
            if index in vectors or index in faces
            for subject_id, subject in self._subjects.items()
            if subject_id not in taken
        )
        pairs = sorted(((s, i, sid) for s, i, sid in scored if s is not None), reverse=True)
        matched: list[tuple[int, int]] = []
        used_tracks: set[int] = set()
        used_subjects: set[int] = set()
        for score, index, subject_id in pairs:
            if index not in used_tracks and subject_id not in used_subjects:
                by, similarity = ("face", score - 1.0) if score > 1.0 else ("body", score)
                logger.debug("Recognized subject #{} by {} ({:.2f})", subject_id, by, similarity)
                self._subjects[subject_id].match = (by, similarity)
                matched.append((index, subject_id))
                used_tracks.add(index)
                used_subjects.add(subject_id)
        return matched

    def _recheck(
        self,
        tracks: list[_Track | None],
        ids: list[int | None],
        vectors: dict[int, np.ndarray],
        faces: dict[int, np.ndarray],
        taken: set[int],
        now: float,
    ) -> None:
        """Merge subjects that turn out to be known ones.

        Provisional subjects are compared by face or body; settled ones only by
        a first clear face, which is strong enough to undo an earlier miss.
        """
        for index, track in enumerate(tracks):
            if track is None:
                continue
            if track.provisional_until is not None and now >= track.provisional_until:
                track.provisional_until = None
            own = track.subject_id
            if track.provisional_until is not None:
                matched = self._match([index], vectors, faces, taken)
            elif index in faces and not self._subjects[own].faces:
                matched = self._match([index], {}, faces, taken)
            else:
                continue
            if not matched:
                continue
            _, known = matched[0]
            self._merge(own, known)
            taken.discard(own)
            taken.add(known)
            ids[index] = known
            track.subject_id = known
            track.provisional_until = None

    def _merge(self, provisional: int, known: int) -> None:
        logger.debug("Subject #{} is subject #{}", provisional, known)
        merged = self._subjects.pop(provisional, None)
        self._aliases[provisional] = known
        if merged is not None:
            target = self._subjects[known]
            for sample in merged.samples:
                self._enroll_body(target, sample, check=False)
            for face in merged.faces:
                self._enroll_face(target, face)

    def _enroll(self, subject: _Subject, vector: np.ndarray | None, face: np.ndarray | None) -> None:
        """Learn how a tracked subject looks now, unless the tracker swapped people."""
        if face is not None and subject.faces:
            if float(np.max(np.stack(subject.faces) @ face)) < FACE_REJECT_THRESHOLD:
                return
        if vector is not None:
            self._enroll_body(subject, vector)
        if face is not None:
            self._enroll_face(subject, face)

    def _enroll_body(self, subject: _Subject, vector: np.ndarray, check: bool = True) -> None:
        """Keep `vector` as a sample of how `subject` looks, if it adds something."""
        vector = np.asarray(vector, dtype=np.float32)
        if subject.samples and self._background is not None:
            similarities = self._centered(subject.samples) @ self._centered(vector)
            best = float(np.max(similarities))
            if check and best < self.consistency_threshold:
                return
            if best >= REDUNDANT:
                return
        subject.samples.append(vector)
        if len(subject.samples) > MAX_SAMPLES and self._background is not None:
            _drop_most_redundant(subject.samples, self._centered(subject.samples))

    @staticmethod
    def _enroll_face(subject: _Subject, face: np.ndarray) -> None:
        if subject.faces and float(np.max(np.stack(subject.faces) @ face)) >= FACE_REDUNDANT:
            return
        subject.faces.append(face)
        if len(subject.faces) > MAX_SAMPLES:
            _drop_most_redundant(subject.faces, np.stack(subject.faces))

    def _canonical(self, subject_id: int) -> int:
        while subject_id in self._aliases:
            subject_id = self._aliases[subject_id]
        return subject_id

    def set_leniency(self, leniency: float) -> float:
        """How readily a returning person is taken to be someone known, from 0
        (strict: fewer mix-ups, more repeat visitors given new IDs) to 1 (lenient)."""
        if not 0.0 <= leniency <= 1.0:
            raise ValueError(f"Leniency must be from 0 to 1, got {leniency}")
        self.leniency = float(leniency)
        self.match_threshold = MATCH_THRESHOLD[0] + (MATCH_THRESHOLD[1] - MATCH_THRESHOLD[0]) * leniency
        self.face_match_threshold = (
            FACE_MATCH_THRESHOLD[0] + (FACE_MATCH_THRESHOLD[1] - FACE_MATCH_THRESHOLD[0]) * leniency
        )
        return self.leniency

    def last_match(self, subject_id: int) -> dict | None:
        """How a subject was last recognized, or None if they have not been yet."""
        with self._lock:
            subject = self._subjects.get(self._canonical(subject_id))
            if subject is None or subject.match is None:
                return None
            return {"by": subject.match[0], "score": round(subject.match[1], 2)}

    def canonical(self, subject_id: int) -> int:
        """The ID a subject goes by now. Differs once a provisional subject is merged."""
        with self._lock:
            return self._canonical(subject_id)

    def is_known(self, subject_id: int) -> bool:
        with self._lock:
            return self._canonical(subject_id) in self._subjects

    def forget_all(self) -> None:
        """Drop every subject. IDs keep counting up so old ones are never reused."""
        with self._lock:
            self._subjects.clear()
            self._tracks.clear()
            self._aliases.clear()

    def status(self) -> dict:
        with self._lock:
            return {
                "known": len(self._subjects),
                "appearance": self.embedder is not None and self._background is not None,
                "faces": self.face_embedder is not None
                and getattr(self.face_embedder, "ready", True),
                "leniency": self.leniency,
            }
