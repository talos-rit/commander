import time

from src.connections import CommandConnection
from src.icd_config import CTypesInt, toBytes


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
