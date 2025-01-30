from config import SOCKET_HOST, SOCKET_PORT
from icd_config import int_to_bytes 
import time
from connections import CommandConnection


class MockOperator:
    connection = CommandConnection(host=SOCKET_HOST, port=SOCKET_PORT)

    @staticmethod
    def close_connection():
        MockOperator.connection.close_socket()

    @staticmethod
    def send_return_code(command_id, payload):
        MockOperator.connection.publish(
            command=command_id,
            payload=payload
        )


def create_return_payload(success):
    return int_to_bytes(int(success), num_bits=16, unsigned=True)


def main():
    while (not MockOperator.connection.is_connected):
        time.sleep(1)

    print("Mock operator is connected!")


if __name__ == "__main__":
    main()
