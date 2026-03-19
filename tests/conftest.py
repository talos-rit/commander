import sys

import pytest

# Prevent application config parsing from consuming pytest CLI args.
# The app config parser uses argparse on sys.argv, which can cause pytest
# arguments (e.g., -k, -q) to be treated as invalid.
sys.argv = [sys.argv[0]]

@pytest.fixture
def no_termination_handlers(monkeypatch):
    """Monkeypatch the termination handler registration functions to avoid issues with global state in utils during tests."""
    def override_helper(module):
        monkeypatch.setattr(module, "add_termination_handler", lambda func: 1)
        monkeypatch.setattr(module, "remove_termination_handler", lambda term: None)

    return override_helper


@pytest.fixture(autouse=True)
def patch_signal(monkeypatch):
    """Prevent tests from changing the real process signal handlers."""

    class DummySignal:
        def __call__(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr("signal.signal", DummySignal())
