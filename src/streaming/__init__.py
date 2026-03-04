from .ffmpeg_streamer import FfmpegStreamController, FfmpegStreamConfig
from .pyvcam_streamer import PyVcamStreamConfig, PyVcamStreamController
from .stream_controller import StreamController, StreamControllerFactory

# Register available stream controllers
# PLEASE make sure to register new stream controllers here when they are implemented
StreamControllerFactory.register("ffmpeg", FfmpegStreamController, FfmpegStreamConfig)
StreamControllerFactory.register("pyvcam", PyVcamStreamController, PyVcamStreamConfig)

__all__ = ["StreamController", "StreamControllerFactory"]
