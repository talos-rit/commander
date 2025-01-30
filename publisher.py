from config import SOCKET_HOST, SOCKET_PORT
from icd_config import Command, int_to_bytes
from connections import OperatorConnection
import time


class Publisher:
    """
    A static class that is used to publish instructions to the operator.
    """
    connection = OperatorConnection(host=SOCKET_HOST, port=SOCKET_PORT)
    command_count = 0

    @staticmethod
    def close_connection():
        Publisher.connection.close_socket()

    @staticmethod
    def handshake():
        # Handshake sends an empty payload 
        payload = b""

        Publisher.connection.publish(
            command=int(Command.HANDSHAKE),
            payload=payload
        )


    @staticmethod
    def polar_pan_discrete(delta_azimuth: int, delta_altitude: int, delay: int, duration: int):
        """
        Delta Azimuth	INT32	Requested change in azimuth
        Delta Altitude	INT32	Requested change in altitude
        Delay (ms)  	UINT32	How long to wait until executing pan
        Duration (ms)	UINT32	How long the pan should take to execute
        """
        delta_azimuth = int_to_bytes(delta_azimuth, num_bits=32, unsigned=False)
        delta_altitude = int_to_bytes(delta_altitude, num_bits=32, unsigned=False)
        delay = int_to_bytes(delay, num_bits=32, unsigned=True)
        duration = int_to_bytes(duration, num_bits=32, unsigned=True)

        # Put everything together
        payload = delta_azimuth + delta_altitude + delay + duration

        Publisher.connection.publish(
            command=int(Command.POLAR_PAN_DISCRETE),
            payload=payload
        )


    @staticmethod
    def polar_pan_continuous_start(moving_azimuth: int = 0, moving_altitude: int = 0):
        """
        Starts/maintains a continuous polar pan rotation.

        Args:
        Moving Azimuth     INT8    -1, 0, or 1
        Moving Altitude    INT8    -1, 0, or 1

        The values in the body describe whether or not the arm is rotating in a given direction. 
        1 rotates counter-clockwise along the axis of movement, -1 rotates clockwise along the axis of 
        movement and 0 means no rotation.
        """
        moving_azimuth = int_to_bytes(moving_azimuth, num_bits=8, unsigned=False)
        moving_altitude = int_to_bytes(moving_altitude, num_bits=8, unsigned=False)

        # Put everything together
        payload = moving_azimuth + moving_altitude

        Publisher.connection.publish(
            command=int(Command.POLAR_PAN_CONTINUOUS_START),
            payload=payload
        )


    @staticmethod
    def polar_pan_continuous_stop():
        """
        Stops a continuous polar pan rotation.
        """
        Publisher.connection.publish(
            command=int(Command.POLAR_PAN_CONTINUOUS_STOP)
        )


    @staticmethod
    def home(delay_ms: int):
        """
        Delay (ms)	UINT32	How long to wait until executing pan
        """
        delay = int_to_bytes(delay_ms, num_bits=32, unsigned=True)

        Publisher.connection.publish(
            command=int(Command.HOME),
            payload=delay
        )


def main():
    while (not Publisher.connection.is_connected):
        time.sleep(1)

    Publisher.home(0)

    # Stay alive
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
