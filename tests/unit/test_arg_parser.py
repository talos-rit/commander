import pytest

from src.arg_parser import _create_arg_parser
from src.config.schema.app import _parse_args
from src.model_options import MODEL_OPTIONS


def test_parse_args_debug_applies_overrides():
    parser = _create_arg_parser()

    args = _parse_args(parser, ["--debug"])

    assert args.debug is True
    assert args.draw_bboxes is True
    assert args.log_level == "DEBUG"


def test_parse_args_without_debug_keeps_defaults():
    parser = _create_arg_parser()

    args = _parse_args(parser, ["--terminal"])

    assert args.debug is False
    assert args.terminal is True
    assert args.draw_bboxes is False
    assert not hasattr(args, "log_level")


def test_parser_accepts_valid_choices():
    parser = _create_arg_parser()

    args = parser.parse_args(
        [
            "--director",
            "discrete",
            "--control-mode",
            "auto",
            "--model",
            MODEL_OPTIONS[0],
        ]
    )

    assert args.director == "discrete"
    assert args.control_mode == "auto"
    assert args.model == MODEL_OPTIONS[0]


def test_parser_rejects_invalid_director_choice():
    parser = _create_arg_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--director", "invalid"])
