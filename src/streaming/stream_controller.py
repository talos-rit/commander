from abc import ABC, abstractmethod
from typing import Callable, Dict, Type

import numpy as np


class StreamConfig(ABC):
    pass


class StreamController(ABC):
    @abstractmethod
    def __init__(
        self, frame_getter: Callable[[], np.ndarray | None], config: StreamConfig
    ) -> None:
        pass

    @abstractmethod
    def start(self) -> None:
        pass

    @abstractmethod
    def stop(self, timeout_s: float = 2.0) -> None:
        pass

    @abstractmethod
    def is_running(self) -> bool:
        pass


class StreamControllerFactory:
    _registry: Dict[str, Type[StreamController]] = {}
    _config_registry: Dict[str, Type[StreamConfig]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        controller_cls: Type[StreamController],
        config_cls: Type[StreamConfig],
    ) -> None:
        cls._registry[name] = controller_cls
        cls._config_registry[name] = config_cls

    @classmethod
    def create(
        cls,
        name: str,
        frame_getter: Callable[[], np.ndarray | None],
        config: dict[str, int | bool | str | None] | None,
    ) -> StreamController:
        if name not in cls._registry:
            raise ValueError(f"Stream controller '{name}' is not registered")
        controller_cls = cls._registry[name]
        config_cls = cls._config_registry[name]
        config_obj = config_cls(**config) if config else config_cls()
        return controller_cls(frame_getter, config_obj)
