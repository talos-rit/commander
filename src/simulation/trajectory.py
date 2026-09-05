"""JSONL robot-state recording and deterministic trajectory replay."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TextIO

from src.robot_state import RobotStateSnapshot, snapshot_from_dict, snapshot_to_dict


FORMAT_NAME = "commander.robot_state"
FORMAT_VERSION = 1


class TrajectoryRecorder:
    def __init__(self, destination: str | Path | TextIO) -> None:
        self._owns_stream = not hasattr(destination, "write")
        self._stream = (
            Path(destination).open("w", encoding="utf-8", newline="\n")
            if self._owns_stream
            else destination
        )

    def record(self, snapshot: RobotStateSnapshot) -> None:
        document = {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "state": snapshot_to_dict(snapshot),
        }
        self._stream.write(json.dumps(document, sort_keys=True) + "\n")
        self._stream.flush()

    def close(self) -> None:
        if self._owns_stream:
            self._stream.close()

    def __enter__(self) -> TrajectoryRecorder:
        return self

    def __exit__(self, *_args) -> None:
        self.close()


class TrajectoryReplay(Iterable[RobotStateSnapshot]):
    """In-memory ordered replay suitable for repeatable passes and visualization."""

    def __init__(self, snapshots: Iterable[RobotStateSnapshot]) -> None:
        self._snapshots = tuple(snapshots)
        if any(
            later.timestamp < earlier.timestamp
            for earlier, later in zip(self._snapshots, self._snapshots[1:])
        ):
            raise ValueError("trajectory timestamps must be nondecreasing")

    @classmethod
    def from_jsonl(cls, source: str | Path | TextIO) -> TrajectoryReplay:
        owns_stream = not hasattr(source, "read")
        stream = (
            Path(source).open("r", encoding="utf-8") if owns_stream else source
        )
        try:
            snapshots = []
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                document = json.loads(line)
                if document.get("format") != FORMAT_NAME:
                    raise ValueError(
                        f"line {line_number}: unsupported trajectory format"
                    )
                if document.get("version") != FORMAT_VERSION:
                    raise ValueError(
                        f"line {line_number}: unsupported trajectory version"
                    )
                snapshots.append(snapshot_from_dict(document["state"]))
            return cls(snapshots)
        finally:
            if owns_stream:
                stream.close()

    def __iter__(self) -> Iterator[RobotStateSnapshot]:
        return iter(self._snapshots)

    def __len__(self) -> int:
        return len(self._snapshots)
