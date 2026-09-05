"""Deterministic prerecorded-video and saved-observation replay utilities."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from .types import FramePacket, ObservationFrame, PersonObservation

if TYPE_CHECKING:
    from src.connection.connection import Connection, VideoConnection


class VideoReplay:
    """Iterate every packet from a prerecorded ``VideoConnection`` exactly once."""

    def __init__(self, video_connection: VideoConnection) -> None:
        self.video_connection = video_connection

    def __iter__(self) -> Iterator[FramePacket]:
        initial_packet = self.video_connection.get_latest_packet()
        if initial_packet is not None:
            yield initial_packet
        while (packet := self.video_connection.capture_packet()) is not None:
            yield packet


class ObservationRecorder:
    """Write frame-batched person observations as stable JSON Lines records."""

    FORMAT_VERSION = 1

    def __init__(self, destination: str | Path | TextIO) -> None:
        if hasattr(destination, "write"):
            self._stream = destination
            self._owns_stream = False
        else:
            self._stream = Path(destination).open("w", encoding="utf-8", newline="\n")
            self._owns_stream = True

    def record(self, frame: ObservationFrame) -> None:
        record = {
            "version": self.FORMAT_VERSION,
            "camera_id": frame.camera_id,
            "frame_sequence": frame.frame_sequence,
            "capture_timestamp": frame.capture_timestamp,
            "observations": [
                {
                    "bounding_box": list(observation.bounding_box),
                    "detection_confidence": observation.detection_confidence,
                    "local_track_id": observation.local_track_id,
                }
                for observation in frame.observations
            ],
        }
        self._stream.write(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        )
        self._stream.flush()

    def close(self) -> None:
        if self._owns_stream:
            self._stream.close()

    def __enter__(self) -> ObservationRecorder:
        return self

    def __exit__(self, *_args) -> None:
        self.close()


class ObservationReplay:
    """Replay saved observations without loading images or running a detector."""

    def __init__(self, source: str | Path | TextIO) -> None:
        self.source = source

    def __iter__(self) -> Iterator[ObservationFrame]:
        if hasattr(self.source, "read"):
            yield from self._read_stream(self.source)
            return
        with Path(self.source).open("r", encoding="utf-8") as stream:
            yield from self._read_stream(stream)

    def replay_into(
        self, connections: Mapping[str, Connection]
    ) -> Iterator[ObservationFrame]:
        """Apply each recorded frame to a matching existing Connection."""

        for frame in self:
            connection = connections.get(frame.camera_id)
            if connection is not None:
                connection.set_observations(list(frame.observations))
            yield frame

    @classmethod
    def _read_stream(cls, stream: TextIO) -> Iterator[ObservationFrame]:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            if raw.get("version") != ObservationRecorder.FORMAT_VERSION:
                raise ValueError(f"unsupported observation format on line {line_number}")
            camera_id = str(raw["camera_id"])
            frame_sequence = int(raw["frame_sequence"])
            capture_timestamp = float(raw["capture_timestamp"])
            observations = tuple(
                PersonObservation(
                    camera_id=camera_id,
                    frame_sequence=frame_sequence,
                    capture_timestamp=capture_timestamp,
                    bounding_box=tuple(item["bounding_box"]),
                    detection_confidence=(
                        float(item["detection_confidence"])
                        if item["detection_confidence"] is not None
                        else None
                    ),
                    local_track_id=(
                        int(item["local_track_id"])
                        if item["local_track_id"] is not None
                        else None
                    ),
                )
                for item in raw["observations"]
            )
            yield ObservationFrame(
                camera_id=camera_id,
                frame_sequence=frame_sequence,
                capture_timestamp=capture_timestamp,
                observations=observations,
            )
