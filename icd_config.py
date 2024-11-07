from enum import Enum
from ctypes import c_int8, c_uint8, c_int16, c_uint16, c_int32, c_uint32


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


class Command(Enum):
    HANDSHAKE = 0x0000
    POLAR_PAN_DISCRETE = 0x0001
    HOME = 0x0002
    POLAR_PAN_CONTINUOUS_START = 0x0003
    POLAR_PAN_CONTINUOUS_STOP = 0x0004

    def __int__(self):
        """
        Used for casting Enum object to integer
        """
        return self.value
