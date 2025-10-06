from tracker import ObjectModel

MODELS: list[ObjectModel.__class__] = list()


try:
    from haar_cascade.basic_model import BasicModel

    MODELS.append(BasicModel)
except ImportError as e:
    print(
        e,
        "Failed to import Haar cascade. This is an optional import, but may limit the ability to run this model",
    )

try:
    from keep_away.keep_away_model import KeepAwayModel
    from media_pipe import MediaPipeModel, MediaPipePoseModel

    MODELS.append(KeepAwayModel)
    MODELS.append(MediaPipeModel)
    MODELS.append(MediaPipePoseModel)
except ImportError as e:
    print(
        e,
        "Failed to import mediapipe. This is an optional import, but may limit the ability to run this model",
    )

try:
    from yolo.yolo_model import YOLOModel

    MODELS.append(YOLOModel)
except ImportError as e:
    print(
        e,
        "Failed to import Yolo model. This is an optional import, but may limit the ability to run this model",
    )
