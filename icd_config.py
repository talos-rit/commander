from enum import Enum
from ctypes import c_uint8, c_uint16, c_uint32


def int_to_bytes(num, num_bits=16):
    """
    Helper function for converting integers to bits
    """
    c_type_int = None

    # Convert to C types accourding to ICD to ensure the correct number of bits.
    # This can be expanded in the future if needed
    if num_bits == 8:
        c_type_int = c_uint8(num)
    elif num_bits == 16:
        c_type_int = c_uint16(num)
    elif num_bits == 32:
        c_type_int = c_uint32(num)
    else:
        raise Exception("Unsupported number of bits given to int_to_bytes")

    # Reverse the bytes to be big-endian. Then convert to bytes.
    return bytes(reversed(bytes(c_type_int)))


class Command(Enum):
    HANDSHAKE = 0x0000
    POLAR_PAN = 0x0001

    def __int__(self):
        """
        Used for casting Enum object to integer
        """
        return self.value
