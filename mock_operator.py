import time

from connections import CommandConnection
from icd_config import int_to_bytes

class MockOperator:
    connection = CommandConnection(host="mock_socket_host", port=420)

    @staticmethod
    def close_connection():
        MockOperator.connection.close()

    @staticmethod
    def send_return_code(command_id, payload):
        MockOperator.connection.publish(command=command_id, payload=payload)


def create_return_payload(success):
    return int_to_bytes(int(success), num_bits=16, unsigned=True)


def main():
    while not MockOperator.connection.is_running:
        time.sleep(1)

    print("Mock operator is connected!")


if __name__ == "__main__":
    main()
