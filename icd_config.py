from enum import Enum

class Command(Enum):
    HANDSHAKE = 0x0000
    POLAR_PAN = 0x0001

    def __int__(self):
        return self.value
