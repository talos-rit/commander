# Demo pose model

`yolo11n-pose-320.onnx` is exported from the project's stock Ultralytics
`yolo11n-pose.pt` weights for fixed batch 1, RGB CHW 320x320 input, dynamic=False,
opset 17, simplify=False. Exported with Ultralytics 8.4.33 / ONNX 1.23.0.

SHA-256: `16dacd1cf8b5a97f93d203e3ad4c2d52ed13da9853a8a706b4f708d6f364d625`.

It is included so container builds do not depend on an untracked Pi-only model.
The original weights/model are from Ultralytics YOLO11; see their upstream model
and licensing information: https://docs.ultralytics.com/models/yolo11/ and
https://www.ultralytics.com/license .
