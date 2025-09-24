from ctypes import c_int8, c_int16, c_int32, c_uint8, c_uint16, c_uint32
from enum import IntEnum


def int_to_bytes(num, num_bits=16, unsigned=True):
    """
    Helper function for converting integers to bits
    """
    c_type_int = None

    # Convert to C types accourding to ICD to ensure the correct number of bits.
    # This can be expanded in the future if needed
    if num_bits == 8:
        if unsigned:
            c_type_int = c_uint8(num)
        else:
            c_type_int = c_int8(num)
    elif num_bits == 16:
        if unsigned:
            c_type_int = c_uint16(num)
        else:
            c_type_int = c_int16(num)
    elif num_bits == 32:
        if unsigned:
            c_type_int = c_uint32(num)
        else:
            c_type_int = c_int32(num)
    else:
        raise Exception("Unsupported number of bits given to int_to_bytes")

    # Reverse the bytes to be big-endian. Then convert to bytes.
    return bytes(reversed(bytes(c_type_int)))


def bytes_to_int(bytes):
    return int.from_bytes(bytes, byteorder="big")


class Command(IntEnum):
    HANDSHAKE = 0x0000
    HANDSHAKE_RETURN = 0x8000
    POLAR_PAN_DISCRETE = 0x0001
    POLAR_PAN_DISCRETE_RETURN = 0x8001
    HOME = 0x0002
    HOME_RETURN = 0x8002
    POLAR_PAN_CONTINUOUS_START = 0x0003
    POLAR_PAN_CONTINUOUS_START_RETURN = 0x8003
    POLAR_PAN_CONTINUOUS_STOP = 0x0004
    POLAR_PAN_CONTINUOUS_STOP_RETURN = 0x8004
    CARTESIAN_MOVE_DISCRETE = 0x0005
    CARTESIAN_MOVE_DISCRETE_RETURN = 0x8005
    CARTESIAN_MOVE_CONTINUOUS_START = 0x0006
    CARTESIAN_MOVE_CONTINUOUS_START_RETURN = 0x8006
    CARTESIAN_MOVE_CONTINUOUS_STOP = 0x0007
    CARTESIAN_MOVE_CONTINUOUS_STOP_RETURN = 0x8007
    EXECUTE_HARDWARE_OPERATION = 0x0008
    EXECUTE_HARDWARE_OPERATION_RETURN = 0x8008
    GET_SPEED = 0x0009
    GET_SPEED_RETURN = 0x8009
    SET_SPEED = 0x000A
    SET_SPEED_RETURN = 0x800A
    SAVE_POSITION = 0x000B
    SAVE_POSITION_RETURN = 0x800B
    DELETE_POSITION = 0x000C
    DELETE_POSITION_RETURN = 0x800C
    GO_TO_POSITION = 0x000D
    GO_TO_POSITION_RETURN = 0x800D
    SET_POLAR_POSITION = 0x000E
    SET_POLAR_POSITION_RETURN = 0x800E
    GET_POLAR_POSITION = 0x000F
    GET_POLAR_POSITION_RETURN = 0x800F
    SET_CARTESIAN_POSITION = 0x0010
    SET_CARTESIAN_POSITION_RETURN = 0x8010
    GET_CARTESIAN_POSITION = 0x0011
    GET_CARTESIAN_POSITION_RETURN = 0x8011

    def __int__(self):
        """
        Used for casting Enum object to integer
        """
        return self.value
