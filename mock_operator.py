from config import SOCKET_HOST, SOCKET_PORT
from icd_config import int_to_bytes, bytes_to_int
from publisher import Publisher, Connection
import time
import threading
import socket


class CommandConnection(Connection):
    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        while(True):
            try:
                self.socket.bind((self.host, self.port))
                self.is_connected = True
                print("Bind to socket: " + self.host + ":" + str(self.port))
                break
            except ConnectionRefusedError: # catch refused connection for retry
                print("Connection to " + self.host + ":" + str(self.port) + " failed, retrying in 5s")
                time.sleep(5)

        self.accept_connections()

    def accept_connections(self):
        print("Starting to listen!")
        self.socket.listen()

        while True: 
            # Establish connection with client. 
            connection, address = self.socket.accept()
            print ('Got connection from', address)
            thread = threading.Thread(target=self.listen, args=(connection,))
            thread.start()

    def listen(self, connection):
        while True:
            message = connection.recv(2048)
            command_id_bytes = message[0:4]
            reserved_bytes = message[4:6]
            command_value_bytes = message[6:8]
            payload_length_bytes = message[8:10]
            
            payload_length = bytes_to_int(payload_length_bytes)
            command_value = bytes_to_int(command_value_bytes)

            payload_end_index = 10 + payload_length
            payload_bytes = message[10:payload_end_index]
            checksum_bytes = message[-2:]

            return_command_value = command_value + 0x8000
            return_command_value_bytes = int_to_bytes(return_command_value, num_bits=16, unsigned=True)
            print("Sending return")
            connection.send(return_command_value_bytes)


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
    Publisher.home(0)


if __name__ == "__main__":
    main()
