"""Start-to-start inference pacing; late frames never create catch-up work."""
import math
import time


class InferenceRate:
    def __init__(self, fps=0.0, clock=time.monotonic):
        if not math.isfinite(fps) or fps < 0:
            raise ValueError("inference FPS must be finite and non-negative (0 = unlimited)")
        self.period = 1.0 / fps if fps else 0.0
        self.clock = clock
        self.next_start = 0.0

    def delay(self):
        return max(0.0, self.next_start - self.clock()) if self.period else 0.0

    def started(self):
        self.next_start = self.clock() + self.period
