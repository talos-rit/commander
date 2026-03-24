import pytest
from pytest_mock import MockerFixture

from src.connection.publisher import Publisher
from src.icd_config import CTypesInt, Command, toBytes

OPERATOR_CONNECTION_PATH = "src.connection.publisher.OperatorConnection"

@pytest.fixture()
def mockOperatorConnection(mocker: MockerFixture):
    yield mocker.patch(OPERATOR_CONNECTION_PATH, autospec=True).return_value


def test_init(mocker):
    mockOperatorConnection = mocker.patch(OPERATOR_CONNECTION_PATH)
    expected_host = "localhost"
    expected_port = 12345
    expected_start_connection = True
    Publisher(expected_host, expected_port, expected_start_connection)

    mockOperatorConnection.assert_called_once_with(
        host=expected_host,
        port=expected_port,
        connect_on_init=expected_start_connection,
    )


def test_close(mockOperatorConnection):
    close_func = mockOperatorConnection.close
    publisher = Publisher("localhost", 12345, True)
    publisher.close()

    close_func.assert_called_once()


def test_handshake(mockOperatorConnection):
    publish_func = mockOperatorConnection.publish
    publisher = Publisher("localhost", 12345, True)
    publisher.handshake()

    publish_func.assert_called_once_with(command=Command.HANDSHAKE, payload=b"")


def test_polar_pan_discrete(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)
    publisher.polar_pan_discrete(delta_azimuth_int=1, delta_altitude_int=-2, delay_int=3, duration_int=4)

    expected_payload = (
        toBytes(1, CTypesInt.INT32)
        + toBytes(-2, CTypesInt.INT32)
        + toBytes(3, CTypesInt.UINT32)
        + toBytes(4, CTypesInt.UINT32)
    )

    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.POLAR_PAN_DISCRETE, payload=expected_payload
    )


def test_polar_pan_continuous_direction_start(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)
    publisher.polar_pan_continuous_direction_start(dir_sum=2)

    expected_payload = toBytes(1, CTypesInt.INT8) + toBytes(1, CTypesInt.INT8)
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.POLAR_PAN_CONTINUOUS_START, payload=expected_payload
    )


def test_polar_pan_continuous_direction_start_invalid_raises(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)

    with pytest.raises(AssertionError):
        publisher.polar_pan_continuous_direction_start(dir_sum=5)


def test_polar_pan_continuous_start_asserts_invalid_values(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)

    with pytest.raises(AssertionError):
        publisher.polar_pan_continuous_start(moving_azimuth_int=2, moving_altitude_int=0)


def test_polar_pan_continuous_start_and_stop(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)
    publisher.polar_pan_continuous_start(moving_azimuth_int=-1, moving_altitude_int=0)

    expected_payload = toBytes(-1, CTypesInt.INT8) + toBytes(0, CTypesInt.INT8)
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.POLAR_PAN_CONTINUOUS_START, payload=expected_payload
    )

    mockOperatorConnection.publish.reset_mock()
    publisher.polar_pan_continuous_stop()
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.POLAR_PAN_CONTINUOUS_STOP
    )


def test_home(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)
    publisher.home(delay_ms=123)

    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.HOME, payload=toBytes(123, CTypesInt.UINT32)
    )


def test_set_speed(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)
    publisher.set_speed(speed=99)

    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.SET_SPEED, payload=toBytes(99, CTypesInt.UINT8)
    )


def test_save_and_delete_and_go_to_position(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)

    publisher.save_position(name="p", anchor=True, parent="root")
    expected_payload = (
        toBytes(1, CTypesInt.UINT8)
        + b"p"
        + b"\x01"
        + toBytes(4, CTypesInt.UINT8)
        + b"root"
    )
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.SAVE_POSITION, payload=expected_payload
    )

    mockOperatorConnection.publish.reset_mock()
    publisher.delete_position(name="p")
    expected_payload = toBytes(1, CTypesInt.UINT8) + b"p"
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.DELETE_POSITION, payload=expected_payload
    )

    mockOperatorConnection.publish.reset_mock()
    publisher.go_to_position(name="p")
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.GO_TO_POSITION, payload=expected_payload
    )


def test_set_get_polar_position(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)
    publisher.set_polar_position(name="here", delta=1, azimuth=2, radius=3)

    expected_payload = (
        toBytes(4, CTypesInt.UINT8)
        + b"here"
        + toBytes(1, CTypesInt.INT32)
        + toBytes(2, CTypesInt.INT32)
        + toBytes(3, CTypesInt.INT32)
    )
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.SET_POLAR_POSITION, payload=expected_payload
    )

    mockOperatorConnection.publish.reset_mock()
    publisher.get_polar_position(name="here")
    expected_payload = toBytes(4, CTypesInt.UINT8) + b"here"
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.GET_POLAR_POSITION, payload=expected_payload
    )


def test_set_get_cartesian_position(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)
    publisher.set_cartesian_position(name="pos", x_mm_tenths=1, y_mm_tenths=2, z_mm_tenths=3)

    expected_payload = (
        toBytes(3, CTypesInt.UINT8)
        + b"pos"
        + toBytes(1, CTypesInt.INT32)
        + toBytes(2, CTypesInt.INT32)
        + toBytes(3, CTypesInt.INT32)
    )
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.SET_CARTESIAN_POSITION, payload=expected_payload
    )

    mockOperatorConnection.publish.reset_mock()
    publisher.get_cartesian_position(name="pos")
    expected_payload = toBytes(3, CTypesInt.UINT8) + b"pos"
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.GET_CARTESIAN_POSITION, payload=expected_payload
    )


def test_get_speed(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)
    publisher.get_speed()

    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.GET_SPEED, payload=b""
    )


def test_cartesian_move_discrete(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)
    publisher.cartesian_move_discrete(delta_x=1, delta_y=2, delta_z=3, delay_ms=4, time=5)

    expected_payload = (
        toBytes(1, CTypesInt.INT32)
        + toBytes(2, CTypesInt.INT32)
        + toBytes(3, CTypesInt.INT32)
        + toBytes(4, CTypesInt.UINT32)
        + toBytes(5, CTypesInt.UINT32)
    )
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.CARTESIAN_MOVE_DISCRETE, payload=expected_payload
    )


def test_cartesian_move_continuous_start_and_stop(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)
    publisher.cartesian_move_continuous_start(moving_x=1, moving_y=0, moving_z=-1)

    expected_payload = (
        toBytes(1, CTypesInt.INT8) + toBytes(0, CTypesInt.INT8) + toBytes(-1, CTypesInt.INT8)
    )
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.CARTESIAN_MOVE_CONTINUOUS_START, payload=expected_payload
    )

    mockOperatorConnection.publish.reset_mock()
    publisher.cartesian_move_continuous_stop()
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.CARTESIAN_MOVE_CONTINUOUS_STOP, payload=b""
    )


def test_execute_hardware_operation(mockOperatorConnection):
    publisher = Publisher("localhost", 12345, True)
    operations_payload = b"abc"
    publisher.execute_hardware_operation(subcommand_value=1, operations_payload=operations_payload)

    expected_payload = (
        toBytes(1, CTypesInt.UINT8) + toBytes(0, CTypesInt.UINT32) + operations_payload
    )
    mockOperatorConnection.publish.assert_called_once_with(
        command=Command.EXECUTE_HARDWARE_OPERATION, payload=expected_payload
    )
