"""Commander-supervised Pi-local autonomy and manual command arbitration."""
import threading
import time

from fastapi import HTTPException


class ControlLease:
    def __init__(self, controller, operator, clock=time.monotonic, ttl=1.5):
        self.controller, self.operator = controller, operator
        self.clock, self.ttl = clock, ttl
        self.owner = None
        self.deadline = 0.0
        self._lock = threading.RLock()

    def update(self, owner, enabled, renew=False):
        if not isinstance(owner, str) or not 8 <= len(owner) <= 128 or type(enabled) is not bool:
            raise HTTPException(422, "expected owner token and boolean enabled")
        with self._lock:
            self.service()
            if renew and (self.owner != owner or not self.controller.enabled):
                raise HTTPException(409, "control lease expired or was revoked; explicitly rearm")
            if self.owner is not None and self.owner != owner:
                raise HTTPException(409, "another Commander owns autonomous control")
            if not enabled:
                self.controller.set_enabled(False)
                self.owner, self.deadline = None, 0.0
            else:
                if not self.controller.set_enabled(True):
                    raise HTTPException(409, self.controller.last_thought)
                self.owner, self.deadline = owner, self.clock() + self.ttl
            return self.status()

    def service(self):
        with self._lock:
            if self.owner is not None and (self.clock() >= self.deadline or not self.controller.enabled):
                expired = self.clock() >= self.deadline
                self.controller.set_enabled(False)
                if expired:
                    self.controller.last_thought = "Commander control lease expired. Tracking stopped; explicitly rearm."
                self.owner, self.deadline = None, 0.0

    def revoke(self):
        with self._lock:
            self.controller.set_enabled(False)
            self.owner, self.deadline = None, 0.0

    def tune(self, owner, acceptable_ratio):
        if not isinstance(owner, str) or not 8 <= len(owner) <= 128:
            raise HTTPException(422, "expected Commander owner token")
        with self._lock:
            self.service()
            if self.owner is not None and self.owner != owner:
                raise HTTPException(409, "another Commander owns autonomous control")
            try:
                self.controller.set_acceptable_ratio(acceptable_ratio)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            return self.status()

    def status(self):
        with self._lock:
            telemetry = self.operator.get_telemetry()
            receipt = getattr(self.operator, "command_receipt", lambda: None)()
            return {"enabled": self.controller.enabled, "owner": self.owner,
                    "state": getattr(getattr(self.controller, "state", None), "value", None),
                    "last_thought": self.controller.last_thought,
                    "acceptable_ratio": getattr(self.controller, "acceptable_ratio", .25),
                    "lease_remaining_s": max(0, self.deadline - self.clock()),
                    "operator_connected": self.operator.is_connected,
                    "fault": self.operator.get_fault(),
                    "joint_counts": [telemetry.base, telemetry.shoulder, telemetry.elbow,
                                     telemetry.wrist_pitch, telemetry.wrist_roll] if telemetry.has_received else None,
                    "telemetry_age_s": self.clock() - telemetry.last_updated_monotonic if telemetry.has_received else None,
                    "commands": receipt}

    def manual_command(self, command, payload):
        # The allowlist mirrors the implemented ER-V protocol. No opaque ACL strings.
        lengths = {0: 0, 1: 16, 2: 4, 3: 2, 4: 0}
        if command == 8:
            if len(payload) < 5 or payload[1:5] != b"\0" * 4:
                raise HTTPException(422, "invalid hardware envelope")
            expected = {1: 7, 2: 5, 3: 17, 4: 5, 5: 6}.get(payload[0])
            if expected != len(payload):
                raise HTTPException(422, "unsupported hardware operation")
        elif command not in lengths or len(payload) != lengths[command]:
            raise HTTPException(422, "unsupported ER-V command or payload length")
        with self._lock:
            self.service()
            # Stops and Home explicitly take control back. Other manual motion
            # requires the lease to have been released first.
            if command in (2, 4) or (command == 8 and payload[0] == 2):
                self.revoke()
            elif self.owner is not None and command != 0:
                raise HTTPException(409, "disable autonomous tracking before manual commands")
            sent = (self.operator.clear_fault() if command == 8 and payload[0] == 4
                    else self.operator.send_command(command, payload))
            if not sent:
                raise HTTPException(503, "Operator command connection unavailable")
            return {"dispatched": True}  # Not controller acceptance or physical completion.
