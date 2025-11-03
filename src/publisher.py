from enum import IntEnum

from connections import Connection
from icd_config import Command, CTypesInt, toBytes
from src.tkscheduler import Scheduler


class Direction(IntEnum):
    """Directional Enum for interface controls

    The values can be summed to get combined directions(from -4 to 4)
    -4: DL, -3: L, -2: UL, -1: D, 0: None, 1: U, 2: DR, 3: R, 4: UR
    """

    UP = 1
    DOWN = -1
    RIGHT = 3
    LEFT = -3

    @staticmethod
    def toDirectionTuple(sum_direction: int) -> tuple[int, int]:
        """Convert Direction enum to (x, y) tuple representation"""
        mapping = {
            0: (0, 0),
            1: (0, 1),
            -1: (0, -1),
            2: (1, 1),
            -2: (-1, -1),
            3: (1, 0),
            -3: (-1, 0),
            4: (1, -1),
            -4: (-1, 1),
        }
        return mapping[sum_direction]


def assert_normalized(*nums: int):
    nums_abs = list(map(lambda x: abs(x), nums))
    return all(map(lambda x: x in [0, 1], nums_abs))


class Publisher:
    """
    A class that is used to publish instructions to the operator.
    """

    command_count = 0
    CHAR_ENCODING = "utf-8"

    def __init__(self, socket_host: str, socket_port: int):
        self.connection = Connection(host=socket_host, port=socket_port)

    def start_socket_connection(self, schedule: Scheduler | None = None):
        self.connection.schedule = schedule
        self.connection.connect_on_thread()

    def close_connection(self):
        self.connection.close()

    def handshake(self):
        # Handshake sends an empty payload
        payload = b""

        self.connection.publish(command=Command.HANDSHAKE, payload=payload)

    def polar_pan_discrete(
        self,
        delta_azimuth_int: int,
        delta_altitude_int: int,
        delay_int: int,
        duration_int: int,
    ):
        """
        Delta Azimuth	INT32	Requested change in azimuth
        Delta Altitude	INT32	Requested change in altitude
        Delay (ms)  	UINT32	How long to wait until executing pan
        Duration (ms)	UINT32	How long the pan should take to execute
        """
        delta_azimuth = toBytes(delta_azimuth_int, CTypesInt.INT32)
        delta_altitude = toBytes(delta_altitude_int, CTypesInt.INT32)
        delay = toBytes(delay_int, CTypesInt.UINT32)
        duration = toBytes(duration_int, CTypesInt.UINT32)

        # Put everything together
        payload = delta_azimuth + delta_altitude + delay + duration

        self.connection.publish(command=Command.POLAR_PAN_DISCRETE, payload=payload)

    def polar_pan_continuous_direction_start(self, dir_sum: int):
        """
        Starts/maintains a continuous polar pan rotation.

        Args:
        Direction   INT8    -4 to 4 (see Direction enum for mapping)

        The values in the body describe whether or not the arm is rotating in a given direction.
        1 rotates counter-clockwise along the axis of movement, -1 rotates clockwise along the axis of
        movement and 0 means no rotation.
        """
        assert dir_sum in range(-4, 5), "Direction sum must be between -4 and 4"
        x_dir, y_dir = Direction.toDirectionTuple(dir_sum)
        return self.polar_pan_continuous_start(x_dir, y_dir)

    def polar_pan_continuous_start(
        self, moving_azimuth_int: int = 0, moving_altitude_int: int = 0
    ):
        """
        Starts/maintains a continuous polar pan rotation.

        Args:
        Moving Azimuth     INT8    -1, 0, or 1
        Moving Altitude    INT8    -1, 0, or 1

        The values in the body describe whether or not the arm is rotating in a given direction.
        1 rotates counter-clockwise along the axis of movement, -1 rotates clockwise along the axis of
        movement and 0 means no rotation.
        """
        assert assert_normalized(moving_azimuth_int, moving_altitude_int)

        moving_azimuth = toBytes(moving_azimuth_int, CTypesInt.INT8)
        moving_altitude = toBytes(moving_altitude_int, CTypesInt.INT8)

        # Put everything together
        payload = moving_azimuth + moving_altitude

        self.connection.publish(
            command=Command.POLAR_PAN_CONTINUOUS_START, payload=payload
        )

    def polar_pan_continuous_stop(self):
        """
        Stops a continuous polar pan rotation.
        """
        self.connection.publish(command=Command.POLAR_PAN_CONTINUOUS_STOP)

    def home(self, delay_ms: int):
        """
        Delay (ms)	UINT32	How long to wait until executing pan
        """
        delay = toBytes(delay_ms, CTypesInt.UINT32)

        self.connection.publish(command=Command.HOME, payload=delay)

    def set_speed(self, speed: int):
        """
        Speed 	UINT8 	What to set the speed of all axes to on the scorbot
        """
        speed_bytes = toBytes(speed, CTypesInt.UINT8)
        self.connection.publish(command=Command.SET_SPEED, payload=speed_bytes)

    def save_position(self, name: str, anchor: bool, parent: str):
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

        name_len_bytes = toBytes(len(name), CTypesInt.UINT8)
        name_bytes = name.encode(self.CHAR_ENCODING)

        anchor_bytes = b"\x01" if anchor else b"\x00"

        parent_len_bytes = toBytes(len(parent), CTypesInt.UINT8)
        parent_bytes = parent.encode(self.CHAR_ENCODING)

        payload = (
            name_len_bytes + name_bytes + anchor_bytes + parent_len_bytes + parent_bytes
        )
        self.connection.publish(command=Command.SAVE_POSITION, payload=payload)

    def delete_position(self, name: str):
        """
        Given a position name, deletes that position information.

        Name    CHAR[]  Name descriptor for the position (non null terminated)
        """

        name_len_bytes = toBytes(len(name), CTypesInt.UINT8)
        name_bytes = name.encode(self.CHAR_ENCODING)

        payload = name_len_bytes + name_bytes
        self.connection.publish(command=Command.DELETE_POSITION, payload=payload)

    def go_to_position(self, name: str):
        """
        Move to a pre-defined position.

        Name    CHAR[]  Name descriptor for the position (non null terminated)
        """
        name_len_bytes = toBytes(len(name), CTypesInt.UINT8)
        name_bytes = name.encode(self.CHAR_ENCODING)

        payload = name_len_bytes + name_bytes
        self.connection.publish(command=Command.GO_TO_POSITION, payload=payload)

    def set_polar_position(self, name: str, delta: int, azimuth: int, radius: int):
        """
        Defines a position in terms of polar coordinates

        Name        CHAR[]  Name descriptor for the position (non null terminated)
        Delta       INT32   Tenths of degrees on delta axis
        Azimuth     INT32   Tenths of degrees on azimuth axis
        Radius      INT32   Tenths of distance to extend outwards
        """

        name_len_bytes = toBytes(len(name), CTypesInt.UINT8)
        name_bytes = name.encode(self.CHAR_ENCODING)

        delta_bytes = toBytes(delta, CTypesInt.INT32)
        azimuth_bytes = toBytes(azimuth, CTypesInt.INT32)
        radius_bytes = toBytes(radius, CTypesInt.INT32)

        payload = (
            name_len_bytes + name_bytes + delta_bytes + azimuth_bytes + radius_bytes
        )
        self.connection.publish(command=Command.SET_POLAR_POSITION, payload=payload)

    def get_polar_position(self, name: str):
        """
        Returns the polar coordinates of a named position

        Name    CHAR[]  Name descriptor for the position (non null terminated)
        """
        name_len_bytes = toBytes(len(name), CTypesInt.UINT8)
        name_bytes = name.encode(self.CHAR_ENCODING)

        payload = name_len_bytes + name_bytes

        self.connection.publish(command=Command.GET_POLAR_POSITION, payload=payload)

    def set_cartesian_position(
        self, name: str, x_mm_tenths: int, y_mm_tenths: int, z_mm_tenths: int
    ):
        """
        Defines a position in terms of cartesian coordinates

        Name    CHAR[]  Name descriptor for the position (non null terminated)
        X       INT32   Tenths of millimeters on X-axis
        Y       INT32   Tenths of millimeters on Y-axis
        Z       INT32   Tenths of millimeters on Z-axis
        """

        name_len_bytes = toBytes(len(name), CTypesInt.UINT8)
        name_bytes = name.encode(self.CHAR_ENCODING)

        x_mm_tenths_bytes = toBytes(x_mm_tenths, CTypesInt.INT32)
        y_mm_tenths_bytes = toBytes(y_mm_tenths, CTypesInt.INT32)
        z_mm_tenths_bytes = toBytes(z_mm_tenths, CTypesInt.INT32)

        payload = (
            name_len_bytes
            + name_bytes
            + x_mm_tenths_bytes
            + y_mm_tenths_bytes
            + z_mm_tenths_bytes
        )
        self.connection.publish(command=Command.SET_CARTESIAN_POSITION, payload=payload)

    def get_cartesian_position(self, name: str):
        """
        Returns the cartesian coordinates of a named position

        Name    CHAR[]  Name descriptor for the position (non null terminated)
        """
        name_len_bytes = toBytes(len(name), CTypesInt.UINT8)
        name_bytes = name.encode(self.CHAR_ENCODING)

        payload = name_len_bytes + name_bytes

        self.connection.publish(command=Command.GET_CARTESIAN_POSITION, payload=payload)

    def get_speed(self):
        """
        Command to get the speed of all axes on Talos
        """
        # Sends an empty payload
        payload = b""

        self.connection.publish(command=Command.GET_SPEED, payload=payload)

    def cartesian_move_discrete(self, delta_x, delta_y, delta_z, delay_ms, time):
        """
        Args:
        Delta X 	INT32 	Requested change in X
        Delta Y 	INT32 	Requested change in Y
        Delta Z 	INT32 	Requested change in Z
        Delay (ms) 	UINT32 	How long to wait until executing pan
        Time 	    UINT32 	How long the pan should take to execute
        """
        delta_x_bytes = toBytes(delta_x, CTypesInt.INT32)
        delta_y_bytes = toBytes(delta_y, CTypesInt.INT32)
        delta_z_bytes = toBytes(delta_z, CTypesInt.INT32)
        delay_ms_bytes = toBytes(delay_ms, CTypesInt.UINT32)
        time_bytes = toBytes(time, CTypesInt.UINT32)
        payload = (
            delta_x_bytes + delta_y_bytes + delta_z_bytes + delay_ms_bytes + time_bytes
        )

        self.connection.publish(
            command=Command.CARTESIAN_MOVE_DISCRETE, payload=payload
        )

    def cartesian_move_continuous_start(self, moving_x, moving_y, moving_z):
        """
        Starts/maintains a continuous cartesian movement.

        Args:
        Moving X 	INT8 	-1, 0, or 1
        Moving Y 	INT8 	-1, 0, or 1
        Moving Z 	INT8 	-1, 0, or 1
        """
        assert assert_normalized(moving_x, moving_y, moving_z)

        moving_x_bytes = toBytes(moving_x, CTypesInt.INT8)
        moving_y_bytes = toBytes(moving_y, CTypesInt.INT8)
        moving_z_bytes = toBytes(moving_z, CTypesInt.INT8)

        payload = moving_x_bytes + moving_y_bytes + moving_z_bytes

        self.connection.publish(
            command=Command.CARTESIAN_MOVE_CONTINUOUS_START, payload=payload
        )

    def cartesian_move_continuous_stop(self):
        """
        Stops a continuous cartesian move.
        """
        # Sends an empty payload
        payload = b""

        self.connection.publish(
            command=Command.CARTESIAN_MOVE_CONTINUOUS_STOP, payload=payload
        )

    def execute_hardware_operation(self, subcommand_value, operations_payload):
        """
        Some operations require high coupling with the specifics of the hardware
        (e.g. axis-by-axis positions). Such operations should be defined by a separate
        companion ICD, to avoid coupling the high level API with the hardware

        Args:
        Subcommand Value 	UINT16 	    Command for function in hardware specific ICD
        RESERVED 	        UINT32 	    RESERVED
        Payload 	        UINT8[] 	Payload defined by hardware specific ICD
        """

        subcommand_value_bytes = toBytes(subcommand_value, CTypesInt.UINT8)
        reserved_bytes = toBytes(0, CTypesInt.UINT32)

        payload = subcommand_value_bytes + reserved_bytes + operations_payload

        self.connection.publish(
            command=Command.EXECUTE_HARDWARE_OPERATION, payload=payload
        )
