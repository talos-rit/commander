import stomp
from icd_config import Command, int_to_bytes


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
        Command ID      UINT32	Unique ID for individual commands
        RESERVED     	UINT16	RESERVED
        Command Value	UINT16	Command for device to carry out
        Length	        UINT16	Length of Payload
        Payload	        UINT8[]	Command Info
        CRC	            UINT16	Checksum
        """
        # Get a unique, incrementing command id
        command_id = Publisher.command_count
        Publisher.command_count += 1

        payload_length = len(payload)
        # TODO: Implement checksum. May get removed
        crc = int_to_bytes(0, num_bits=16)

        command_id = int_to_bytes(command_id, num_bits=32)
        reserved = int_to_bytes(0, num_bits=16)
        command = int_to_bytes(command, num_bits=16)
        payload_length = int_to_bytes(payload_length, num_bits=16)

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
    command_count = 0


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
        delta_azimuth = int_to_bytes(delta_azimuth, num_bits=32)
        delta_altitude = int_to_bytes(delta_altitude, num_bits=32)
        delay = int_to_bytes(delay, num_bits=32)
        duration = int_to_bytes(duration, num_bits=32)

        # Put everything together
        payload = delta_azimuth + delta_altitude + delay + duration

        Publisher.connection.publish(
                destination=INSTRUCTIONS_DESTINATION,
                command=int(Command.POLAR_PAN),
                payload=payload
        )

