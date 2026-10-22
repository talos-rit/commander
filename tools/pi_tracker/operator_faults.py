"""Bounded fault relay for older Operator builds that only log ACL errors."""
from pathlib import Path


class OperatorFaultLog:
    def __init__(self, path="/etc/talos/logs/operator.log"):
        self.path = Path(path)
        self.offset = None
        self.identity = None
        self.pending = b""

    def poll(self):
        try:
            stat = self.path.stat()
            identity = (stat.st_dev, stat.st_ino)
            if self.identity != identity or self.offset is None or stat.st_size < self.offset:
                self.identity = identity
                self.offset = max(0, stat.st_size - 8192)
                self.pending = b""
            with self.path.open("rb") as source:
                source.seek(self.offset)
                data = source.read(8192)
                self.offset = source.tell()
        except OSError:
            return []
        lines = (self.pending + data).split(b"\n")
        self.pending = lines.pop()[-2048:]
        faults = []
        for raw in lines:
            line = raw.decode("utf-8", "replace")
            if "ACL RX:" not in line:
                continue
            message = line.split("ACL RX:", 1)[1].strip()
            if any(word in message.upper() for word in
                   ("IMPACT", "CONTROL DISABLED", "FAULT", "ERROR", "UNRECOGNIZED REQUEST", "NOT FOUND")):
                faults.append(message[:1000])
        return faults
