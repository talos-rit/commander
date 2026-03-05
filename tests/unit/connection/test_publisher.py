import pytest
from pytest_mock import MockerFixture

from src.connection.publisher import Publisher
from src.icd_config import Command

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


def test_polar_pan_discrete():
    pass


def test_polar_pan_continuous_direction_start():
    pass


def test_polar_pan_continuous_start():
    pass


def test_polar_pan_continuous_stop():
    pass


def test_home():
    pass


def test_set_speed():
    pass


def test_save_position():
    pass


def test_delete_position():
    pass


def test_go_to_position():
    pass


def test_set_polar_position():
    pass


def test_get_polar_position():
    pass


def test_set_cartesian_position():
    pass


def test_get_cartesian_position():
    pass


def test_get_speed():
    pass


def test_cartesian_move_discrete():
    pass


def test_cartesian_move_continuous_start():
    pass


def test_cartesian_move_continuous_stop():
    pass


def test_execute_hardware_operation():
    pass
