import stomp
from icd_config import Command 


HANDSHAKE_DESTINATION = '/queue/handshake'
INSTRUCTIONS_DESTINATION = '/queue/instructions'


class Connection:
    """
    The publisher class does not have an initialization since it is a static class.
    This class exists to initialize a single connection instance that is used by the
    publisher. Also contains a function that is used to publish messages.
    """
    def __init__(self):
        self.connection = stomp.Connection()
        self.connection.connect('admin', 'admin', wait=True)

    def publish(self, destination, command: int, payload: bytes):
        """
        Command ID	    UINT32	Unique ID for individual commands
        RESERVED     	UINT16	RESERVED
        Command Value	UINT16	Command for device to carry out
        Length	        UINT16	Length of Payload
        Payload	        UINT8[]	Command Info
        CRC	            UINT16	Checksum
        """
        # TODO: Implement incrementing command IDs
        command_id = 0

        payload_length = len(payload)
        # TODO: Add reserved slot
        header = bytearray([command_id, command, payload_length])
        # TODO: Implement checksum. May get removed
        crc = b""

        """
        TODO: How can we ensure that the bytes are the correct size? For example,
        if we pass in a 0 for an expected UINT16, how can we ensure that it is 2 bytes
        and not 1? Additionally, how can we reserve the "RESERVED" slot?
        """

        # Cast bytearrays to bytes
        body = b"" + header + payload + crc

        self.connection.send(body=body, destination=destination)


class Publisher:
    """
    A static class that is used to publish instructions to the operator.
    """
    connection = Connection()

    @staticmethod
    def handshake():
        # Placeholder
        payload = b""

        Publisher.connection.publish(
                destination=HANDSHAKE_DESTINATION,
                command=int(Command.HANDSHAKE),
                payload=payload
        )

    @staticmethod
    def polar_pan():
        # TODO: Add parameters and put them in the payload
        # Placeholder
        payload = b""

        Publisher.connection.publish(
                destination=INSTRUCTIONS_DESTINATION,
                command=int(Command.POLAR_PAN),
                payload=payload
        )

