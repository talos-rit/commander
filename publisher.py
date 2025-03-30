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
    CHAR_ENCODING = 'utf-8'

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
    def save_position(name: str, anchor: bool, parent: str):
        """
        Saves a position. 

        If this command is sent with a name that already exists, 
        it will be overwritten with the new arguments.
        If reference is an empty string (length of 0), 
        the default value will be used (can be reconfigured, unconfigured default is empty string).
        If the reference string is empty, 
        the Anchor value is ignored and the position is always treated as if anchor is set to false.

        Name    CHAR[]      Name descriptor for the position (non null terminated)
        Anchor  BOOLEAN     Whether the position will move relative to the parent position (0x01 for True, 0x00 for False)
        Parent  CHAR[]      Another previously saved position to act as a parent (or refernce) position
        """

        name_len_bytes  = int_to_bytes(len(name), num_bits=8, unsigned=True)
        name_bytes = name.encode(Publisher.CHAR_ENCODING)

        anchor_bytes = b'\x01' if anchor else b'\x00'

        parent_len_bytes = int_to_bytes(len(parent), num_bits=8, unsigned=True)
        parent_bytes = parent.encode(Publisher.CHAR_ENCODING)

        payload = name_len_bytes + name_bytes + anchor_bytes + parent_len_bytes + parent_bytes
        Publisher.connection.publish(
            command=Command.SAVE_POSITION,
            payload=payload
        )
    
    @staticmethod
    def delete_position(name: str):
        """
        Given a position name, deletes that position information. 

        Name    CHAR[]  Name descriptor for the position (non null terminated)
        """

        name_len_bytes = int_to_bytes(len(name), num_bits=8, unsigned=True)
        name_bytes = name.encode(Publisher.ENCODING)

        payload = name_len_bytes + name_bytes
        Publisher.connection.publish(
            command=Command.DELETE_POSITION,
            payload=payload
        )

    @staticmethod
    def go_to_position(name: str):
        """
        Move to a pre-defined position. 

        Name    CHAR[]  Name descriptor for the position (non null terminated)
        """
        name_len_bytes = int_to_bytes(len(name), num_bits=8, unsigned=True)
        name_bytes = name.encode(Publisher.ENCODING)

        payload = name_len_bytes + name_bytes
        Publisher.connection.publish(
            command=Command.GO_TO_POSITION,
            payload=payload
        )
    
    @staticmethod
    def set_polar_position(name: str, delta: int, azimuth: int, radius: int):
        """
        Defines a position in terms of polar coordinates

        Name        CHAR[]  Name descriptor for the position (non null terminated)
        Delta       INT32   Tenths of degrees on delta axis 
        Azimuth     INT32   Tenths of degrees on azimuth axis 
        Radius      INT32   Tenths of distance to extend outwards 
        """

        name_len_bytes = int_to_bytes(len(name), num_bits=8, unsigned=True)
        name_bytes = name.encode(Publisher.ENCODING)

        delta_bytes = int_to_bytes(delta, num_bits=32, unsigned=False)
        azimuth_bytes = int_to_bytes(azimuth, num_bits=32, unsigned=False)
        radius_bytes = int_to_bytes(radius, num_bits=32, unsigned=False)

        payload = name_len_bytes + name_bytes + delta_bytes + azimuth_bytes + radius_bytes
        Publisher.connection.publish(
            command=Command.SET_POLAR_POSITION,
            payload=payload
        )
    
    @staticmethod
    def get_polar_position(name: str):
        """
        Returns the polar coordinates of a named position

        Name    CHAR[]  Name descriptor for the position (non null terminated)
        """
        name_len_bytes = int_to_bytes(len(name), num_bits=8, unsigned=True)
        name_bytes = name.encode(Publisher.CHAR_ENCODING)

        payload = name_len_bytes + name_bytes

        Publisher.connection.publish(
            command=Command.GET_POLAR_POSITION,
            payload=payload
        )
    
    @staticmethod
    def set_cartesian_position(name: str, x_mm_tenths: int, y_mm_tenths: int, z_mm_tenths: int):
        """
        Defines a position in terms of cartesian coordinates

        Name    CHAR[]  Name descriptor for the position (non null terminated)
        X       INT32   Tenths of millimeters on X-axis 
        Y       INT32   Tenths of millimeters on Y-axis 
        Z       INT32   Tenths of millimeters on Z-axis 
        """

        name_len_bytes = int_to_bytes(len(name), num_bits=8, unsigned=True)
        name_bytes = name.encode(Publisher.CHAR_ENCODING)

        x_mm_tenths_bytes = int_to_bytes(x_mm_tenths, num_bits=32, unsigned=False)
        y_mm_tenths_bytes = int_to_bytes(y_mm_tenths, num_bits=32, unsigned=False)
        z_mm_tenths_bytes = int_to_bytes(z_mm_tenths, num_bits=32, unsigned=False)


        payload = name_len_bytes + name_bytes + x_mm_tenths_bytes + y_mm_tenths_bytes + z_mm_tenths_bytes
        Publisher.connection.publish(
            command=Command.SET_CARTESIAN_POSITION,
            payload=payload
        )
    
    @staticmethod
    def get_cartesian_position(name: str):
        """
        Returns the cartesian coordinates of a named position

        Name    CHAR[]  Name descriptor for the position (non null terminated)
        """
        name_len_bytes = int_to_bytes(len(name), num_bits=8, unsigned=True)
        name_bytes = name.encode(Publisher.CHAR_ENCODING)

        payload = name_len_bytes + name_bytes

        Publisher.connection.publish(
            command=Command.GET_CARTESIAN_POSITION,
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
