import pytest

from src.icd_config import CTypesInt, Command, toBytes, toInt


@pytest.mark.parametrize(
    "value,type_,expected",
    [
        (1, CTypesInt.INT8, b"\x01"),
        (-1, CTypesInt.INT8, b"\xff"),
        (255, CTypesInt.UINT8, b"\xff"),
        (1, CTypesInt.INT16, b"\x00\x01"),
        (-1, CTypesInt.INT16, b"\xff\xff"),
        (0x1234, CTypesInt.UINT16, b"\x12\x34"),
        (0x01020304, CTypesInt.UINT32, b"\x01\x02\x03\x04"),
    ],
)
def test_to_bytes_endianness_and_sign(value, type_, expected):
    """toBytes should return big-endian bytes for ctypes integers."""

    result = toBytes(value, type_)

    assert result == expected


@pytest.mark.parametrize(
    "raw_bytes,expected",
    [
        (b"\x00\x01", 1),
        (b"\xff\xff", 65535),
        (b"\x01\x02\x03\x04", 0x01020304),
    ],
)
def test_to_int_parses_big_endian_bytes(raw_bytes, expected):
    assert toInt(raw_bytes) == expected


def test_command_int_values_are_unique():
    """Ensure Command enum values can be cast to int and are unique."""

    seen = set()
    for cmd in Command:
        value = int(cmd)
        assert value not in seen
        seen.add(value)
