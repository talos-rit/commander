from .base import YOLOBaseModel, YOLOModelSize


class YOLONanoModel(YOLOBaseModel):
    model_size: YOLOModelSize = YOLOModelSize.NANO


class YOLOSmallModel(YOLOBaseModel):
    model_size: YOLOModelSize = YOLOModelSize.SMALL


class YOLOMediumModel(YOLOBaseModel):
    model_size: YOLOModelSize = YOLOModelSize.MEDIUM


class YOLOLargeModel(YOLOBaseModel):
    model_size: YOLOModelSize = YOLOModelSize.LARGE


class YOLOXLargeModel(YOLOBaseModel):
    model_size: YOLOModelSize = YOLOModelSize.XLARGE
