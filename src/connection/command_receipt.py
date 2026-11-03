"""What Commander can know after it asks Operator to move.

Operator replies as soon as a complete ICD frame has been copied into its
command queue (see ``Socket::poll`` in the Operator repo). That is a receive
receipt. It is not tied to the command id, it is not the ``0x8000`` return
messages declared in the ICD, and it is sent before the arm is asked to move.
Nothing in this link reports that a motion finished.

The current Operator build sends ``static const char resp[] = "ACK\\n"``.
``std::span`` over that array includes the terminating NUL, so the bytes are
``ACK\\n\\0``. An older build sent ``ACK\\0`` with no newline.
"""

import threading
import time
from dataclasses import dataclass

# Older Operator: ``char resp[] = "ACK"`` and span sends the trailing NUL.
ACK_TOKEN = b"ACK\x00"
# Current Operator: ``char resp[] = "ACK\n"``. Span sends the newline and the NUL.
ACK_LINE = b"ACK\n"

COMMAND_LABELS = {
    0: "Handshake",
    1: "Aim",
    2: "Home",
    3: "Jog",
    4: "Stop",
    5: "Move",
    6: "Extend",
    7: "Stop",
    8: "Hardware",
    9: "Read speed",
    10: "Speed",
}

HARDWARE_LABELS = {
    0x01: "Joint jog",
    0x02: "Stop joint",
    0x03: "Joint move",
    0x04: "Enable control",
    0x05: "Speed",
    0x06: "Tracking jog",
}


def command_label(command: int, payload: bytes | None = None) -> str:
    """Short name for the last command a person can see in the console."""
    if int(command) == 8 and payload:
        return HARDWARE_LABELS.get(payload[0], "Hardware")
    return COMMAND_LABELS.get(int(command), f"Command {int(command)}")


def strip_acks(buffer: bytes) -> tuple[bytes, int]:
    """Pull Operator receive-receipts out of a mixed telemetry stream.

    A receipt can arrive between newline-terminated ``TEL`` / ``TELP`` lines,
    or split across reads. A trailing partial token is left in place. A
    newline receipt is taken as soon as the newline arrives; a NUL that follows
    it in the same buffer is consumed too. A NUL that arrives in the next read
    is left at the front of the buffer for the caller to drop.
    """
    count = 0
    while True:
        nul_at = buffer.find(ACK_TOKEN)
        line_at = buffer.find(ACK_LINE)
        if nul_at == -1 and line_at == -1:
            return buffer, count
        if line_at != -1 and (nul_at == -1 or line_at < nul_at):
            end = line_at + len(ACK_LINE)
            if end < len(buffer) and buffer[end : end + 1] == b"\x00":
                end += 1
            buffer = buffer[:line_at] + buffer[end:]
            count += 1
            continue
        buffer = buffer[:nul_at] + buffer[nul_at + len(ACK_TOKEN) :]
        count += 1


@dataclass
class CommandReceipt:
    """Counts for one Operator link. ``acked is None`` when this link cannot see receipts."""

    sent: int = 0
    acked: int | None = 0
    last_command: str | None = None
    last_sent_monotonic: float | None = None
    last_ack_monotonic: float | None = None
    last_failed: bool = False

    def note_sent(self, label: str, *, ok: bool, now: float | None = None) -> None:
        moment = time.monotonic() if now is None else now
        self.last_command = label
        self.last_sent_monotonic = moment
        self.last_failed = not ok
        if ok:
            self.sent += 1

    def note_ack(self, count: int = 1, *, now: float | None = None) -> None:
        if count <= 0 or self.acked is None:
            return
        self.acked += count
        self.last_ack_monotonic = time.monotonic() if now is None else now

    def to_dict(self, *, now: float | None = None) -> dict | None:
        if self.sent == 0 and not self.last_failed:
            return None
        moment = time.monotonic() if now is None else now

        def age(stamp: float | None) -> float | None:
            return None if stamp is None else round(moment - stamp, 3)

        return {
            "sent": self.sent,
            "acked": self.acked,
            "last_command": self.last_command,
            "last_sent_age_s": age(self.last_sent_monotonic),
            "last_ack_age_s": age(self.last_ack_monotonic),
            "last_failed": self.last_failed,
        }


class CommandReceiptLog:
    """Thread-safe receipt log shared by a socket reader and the command sender."""

    def __init__(self, *, acks_known: bool = True) -> None:
        self._lock = threading.Lock()
        self._receipt = CommandReceipt(acked=0 if acks_known else None)

    def note_sent(self, label: str, *, ok: bool) -> None:
        with self._lock:
            self._receipt.note_sent(label, ok=ok)

    def note_ack(self, count: int = 1) -> None:
        with self._lock:
            self._receipt.note_ack(count)

    def to_dict(self) -> dict | None:
        with self._lock:
            return self._receipt.to_dict()
