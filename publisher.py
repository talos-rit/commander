import stomp
from icd_config import Command 
from ctypes import c_uint32, c_uint16


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
        # Get a unique, incrementing command id
        command_id = Publisher.get_command_count(command)
        Publisher.increment_command_count(command)

        payload_length = len(payload)
        # TODO: Implement checksum. May get removed
        crc = bytes(c_uint16(0))

        # Convert to C types accourding to ICD to ensure the correct number of bits.
        # Then convert to bytes.
        command_id = bytes(c_uint32(command_id))
        reserved = bytes(c_uint16(0))
        command = bytes(c_uint16(command))
        payload_length = bytes(c_uint16(payload_length))

        # Put header together
        header = command_id + reserved + command + payload_length

        # Put everything together 
        body = header + payload + crc

        self.connection.send(body=body, destination=destination)


class Publisher:
    """
    A static class that is used to publish instructions to the operator.
    """
    connection = Connection()
    command_counts = {}


    def get_command_count(command: int) -> int:
        """
        Simple getter for the number of times a command has been used.
        """
        if command not in Publisher.command_counts:
            return 0
        else:
            return Publisher.command_counts[command]


    def increment_command_count(command: int):
        Publisher.command_counts[command] = Publisher.get_command_count(command) + 1


    @staticmethod
    def handshake():
        # Handshake sends an empty payload 
        payload = b""

        Publisher.connection.publish(
                destination=HANDSHAKE_DESTINATION,
                command=int(Command.HANDSHAKE),
                payload=payload
        )


    @staticmethod
    def polar_pan(delta_azimuth: int, delta_altitude: int, delay: int, duration: int):
        """
        Delta Azimuth	INT32	Requested change in azimuth
        Delta Altitude	INT32	Requested change in altitude
        Delay (ms)  	INT32	How long to wait until executing pan
        Duration (ms)	INT32	How long the pan should take to execute
        """
        # Convert to C types accourding to ICD to ensure the correct number of bits.
        # Then convert to bytes.
        delta_azimuth = bytes(c_uint32(delta_azimuth))
        delta_altitude = bytes(c_uint32(delta_altitude))
        delay = bytes(c_uint32(delay))
        duration = bytes(c_uint32(duration))

        # Put everything together
        payload = delta_azimuth + delta_altitude + delay + duration

        Publisher.connection.publish(
                destination=INSTRUCTIONS_DESTINATION,
                command=int(Command.POLAR_PAN),
                payload=payload
        )

