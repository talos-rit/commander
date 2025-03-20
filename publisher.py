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


    @staticmethod
    def set_speed(speed: int):
        """
        Speed 	UINT8 	What to set the speed of all axes to on the scorbot
        """
        speed_bytes = int_to_bytes(speed, num_bits=8, unsigned=True)

        Publisher.connection.publish(
            command=Command.SET_SPEED,
            payload=speed_bytes
        )


    @staticmethod
    def get_speed():
        """
        Command to get the speed of all axes on Talos
        """
        # Sends an empty payload 
        payload = b""

        Publisher.connection.publish(
            command=Command.GET_SPEED,
            payload=payload
        )


    @staticmethod
    def cartesian_move_discrete():
        """
        Args:
        Delta X 	INT32 	Requested change in X
        Delta Y 	INT32 	Requested change in Y
        Delta Z 	INT32 	Requested change in Z
        Delay (ms) 	UINT32 	How long to wait until executing pan
        Time 	    UINT32 	How long the pan should take to execute
        """
        payload = ""

        Publisher.connection.publish(
            command=Command.CARTESIAN_MOVE_DISCRETE,
            payload=payload
        )


    @staticmethod
    def cartesian_move_continuous_start():
        """
        Starts/maintains a continuous cartesian movement.

        Args:
        Moving X 	INT8 	-1, 0, or 1
        Moving Y 	INT8 	-1, 0, or 1
        Moving Z 	INT8 	-1, 0, or 1
        """
        payload = ""

        Publisher.connection.publish(
            command=Command.CARTESIAN_MOVE_CONTINUOUS_START,
            payload=payload
        )


    @staticmethod
    def cartesian_move_continuous_stop():
        """
        Stops a continuous cartesian move.
        """
        # Sends an empty payload 
        payload = b""

        Publisher.connection.publish(
            command=Command.CARTESIAN_MOVE_CONTINUOUS_STOP,
            payload=payload
        )


    @staticmethod
    def execute_hardware_operation():
        """
        Some operations require high coupling with the specifics of the hardware 
        (e.g. axis-by-axis positions). Such operations should be defined by a separate 
        companion ICD, to avoid coupling the high level API with the hardware

        Args:
        Subcommand Value 	UINT16 	Command for function in hardware specific ICD
        RESERVED 	        UINT32 	RESERVED
        Payload 	        UINT8[] 	Payload defined by hardware specific ICD
        """
        payload = ""

        Publisher.connection.publish(
            command=Command.EXECUTE_HARDWARE_OPERATION,
            payload=payload
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
