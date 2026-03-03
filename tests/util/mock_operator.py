import time

from src.icd_config import CTypesInt, toBytes, toInt

from ...src.connection.publisher import OperatorConnection


class CommandConnection(OperatorConnection):
    """Connection Class used for Mock Operator. This is a receiving socket class.

    Args:
        host: Host to bind the socket to usually localhost for dev
        port: Port to bind the socket to usually 8000 for dev
    """

    def on_message(self, message: bytes):
        command_value_bytes = message[6:8]
        command_value = toInt(command_value_bytes)
        return_command_value = command_value + 0x8000
        return_command_value_bytes = toBytes(return_command_value, CTypesInt.UINT16)
        self.socket.send(return_command_value_bytes)


class MockOperator:
    connection = CommandConnection(host="mock_socket_host", port=420)

    @staticmethod
    def close_connection():
        MockOperator.connection.close()

    @staticmethod
    def send_return_code(command_id, payload):
        MockOperator.connection.publish(command=command_id, payload=payload)


def create_return_payload(success):
    return toBytes(int(success), CTypesInt.UINT16)


def main():
    while not MockOperator.connection.is_running:
        time.sleep(1)

    print("Mock operator is connected!")


if __name__ == "__main__":
    main()
