# Frame ownership and replay

`VideoConnection` owns each camera's monotonically increasing frame sequence and
latest `FramePacket`. A packet contains the camera ID, sequence, capture timestamp,
and the exact NumPy image returned by the source.

Within the Commander application, `Tracker.capture_frames()` is the scheduled frame
producer. It reads every source once, then atomically replaces its latest multi-camera
batch. Detector consumes that batch; Streamer reads each `VideoConnection`'s cached
packet and never advances a source. Streamer copies an image before drawing overlays
so it cannot modify the image being used for detection.

`VideoReplay` is an alternate explicit producer for offline use. It must not run at
the same time as the scheduled Tracker capture loop for the same `VideoConnection`.

## Remaining synchronization limitations

- `VideoConnection.get_frame()` remains as a backward-compatible advancing method.
  No production component in this repository calls it now, but external callers or
  old tests can still advance a source outside Tracker. New code must use
  `capture_packet()`, `get_latest_packet()`, or `get_latest_frame()` explicitly.
- Cameras in one Tracker capture cycle are read sequentially, not hardware-triggered
  simultaneously. Their individual capture timestamps expose this skew; the atomic
  batch only prevents consumers from seeing a partially assembled cycle.
- OpenCV file timestamps use `CAP_PROP_POS_MSEC`. Local camera sources use the
  injectable timestamp provider, and RTSP/PyAV uses its decoded frame timestamp when
  available. Clock synchronization between different physical cameras is not yet
  provided.
- The detector still copies the combined image into and out of shared memory. Those
  are copies of the same `FramePacket` images, not additional source acquisitions.
- A `VideoConnection` acquires its initial valid packet during construction so image
  shape and dtype are available. Failed reads do not consume sequence numbers.

## Observation recording

JSONL records are grouped by source frame rather than by detection. This preserves
zero-detection frames and therefore target-loss timing. Images are intentionally not
stored in the observation stream; `ObservationReplay` can drive future algorithms
from saved observations without loading a model or decoding the original video.
