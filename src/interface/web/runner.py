import contextlib
import multiprocessing.managers
from collections.abc import Generator
from types import FrameType
from typing import Callable

import uvicorn
from loguru import logger

import src.config as config
from src.talos_app import App
from src.thread_scheduler import ThreadScheduler
from src.utils import ensure_termination_guard

from .backend import CommanderWebBackend
from .server import create_web_app, web_dist_available
from .state import WebOperatorState


def build_backend(args=None) -> CommanderWebBackend:
    """Create the backend without opening connections; call startup() for that."""
    settings = config.APP_SETTINGS
    smm = multiprocessing.managers.SharedMemoryManager()
    app = App(ThreadScheduler(), smm=smm, args=args)
    state = WebOperatorState.from_settings(settings)
    if state.camera_1 is None and args is not None and args.connection:
        state.assign_slots(args.connection, None)
    return CommanderWebBackend(app, state)


def run_web(args=None) -> None:
    settings = config.APP_SETTINGS
    ensure_termination_guard()
    backend = build_backend(args)
    url = f"http://{settings.web_host}:{settings.web_port}"
    web_app = create_web_app(backend)
    # timeout_graceful_shutdown defaults to waiting forever for open connections,
    # which the MJPEG feeds always are. It is a backstop; streams are ended first.
    server = _Server(
        uvicorn.Config(
            web_app,
            host=settings.web_host,
            port=settings.web_port,
            log_level="warning",
            timeout_graceful_shutdown=2,
        ),
        on_started=lambda: _on_started(backend, url),
        on_exit=web_app.state.streams_stopping.set,
        before_cleanup=backend.cancel_startup,
    )
    server.run()


def _on_started(backend: CommanderWebBackend, url: str) -> None:
    if web_dist_available():
        logger.info(f"Commander web UI running at {url} (connecting to cameras...)")
    else:
        logger.warning(
            f"Serving API only at {url}/api. From web/, run `bun install` and `bun run build`, "
            "or run `bun --cwd web run dev` and open http://localhost:5173"
        )
    backend.start_in_background()


class _Server(uvicorn.Server):
    """uvicorn server that opens connections once it is listening and ends
    MJPEG streams as soon as Ctrl+C is pressed."""

    def __init__(
        self,
        config: uvicorn.Config,
        on_exit: Callable[[], None],
        on_started: Callable[[], None] = lambda: None,
        before_cleanup: Callable[[], None] = lambda: None,
    ):
        super().__init__(config)
        self._on_exit = on_exit
        self._on_started = on_started
        self._before_cleanup = before_cleanup

    async def startup(self, sockets=None) -> None:
        await super().startup(sockets)
        if self.started:
            self._on_started()

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        self._on_exit()
        super().handle_exit(sig, frame)

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        # uvicorn re-raises the captured Ctrl+C after this block, which runs
        # Commander's termination handlers; startup must not still be adding
        # connections when they do.
        with super().capture_signals():
            try:
                yield
            finally:
                self._before_cleanup()
