import atexit
import socket
import threading
import time

from icd_config import bytes_to_int, int_to_bytes


class Connection:
    """Base Connection Class, Creates Socket connection on initialization."""

    is_running = False
    command_count = 0

    def __init__(self, host, port, connect_on_init=True):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if connect_on_init:
            # Start connection on a separate thread so it doesn't block
            self.connect_on_thread()

    def connect_on_thread(self):
        thread = threading.Thread(target=self.connect)
        thread.start()
        atexit.register(self.close)  # Run close when the program is exiting
        return thread

    def connect(self):
        self.is_running = True
        while self.is_running:
            try:
                self.socket.bind((self.host, self.port))
                print(f"Bound to socket: {self.host}:{self.port}")
                break
            except OSError as e:
                print(f"[Connection]: Bind failed, retrying in 5s {e}")
                time.sleep(5)
        else:
            return  # Exit only if is_running was set to False

        print("Starting to listen!")
        self.socket.listen()
        while self.is_running:
            try:
                connection, address = self.socket.accept()
                print("Got connection from", address)
                self.listen(connection)
            except OSError as e:
                print("OS Error:", e)
                break

    def close(self):
        """Cleanly close the socket port and stop listening to new connections."""
        self.socket.close()
        self.is_running = False
        print("Socket closed cleanly")

    def publish(self, command: int, payload: bytes | None = None):
        """
        Command ID      UINT32	Unique ID for individual commands
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        RESERVED     	UINT16	RESERVED
        Command Value	UINT16	Command for device to carry out
        Length	        UINT16	Length of Payload
        Payload	        UINT8[]	Command Info
        CRC	            UINT16	Checksum
        """
        # Get a unique, incrementing command id. Increment by 2, so that the response
        # from the operator always returns odd command ids and the publisher always sends
        # even command ids. Commands can be associated with each other by checking if they
        # have the same modulus of 2.
        command_id = self.command_count
        self.command_count += 2
        payload_length = 0 if payload is None else len(payload)

        # TODO: Implement checksum. May get removed
        crc = int_to_bytes(0, num_bits=16, unsigned=True)

        command_id = int_to_bytes(command_id, num_bits=32, unsigned=True)
        reserved = int_to_bytes(0, num_bits=16, unsigned=True)
        command_byte = int_to_bytes(command, num_bits=16, unsigned=True)
        payload_length = int_to_bytes(payload_length, num_bits=16, unsigned=True)

        # Put header together
        header = command_id + reserved + command_byte + payload_length

        # Put everything together
        message = header

        if payload is not None:
            message += payload
        message += crc

        try:
            self.socket.sendall(message)  # safer than send()
        except OSError as e:
            print(f"Socket send failed: {e}")
            return -1

        # TODO: Implement response handling if needed
        # response = self.socket.recv(2048)
        return 0

    def listen(self, connection: socket.socket):
        while self.is_running:
            message = connection.recv(2048)
            if not message:
                break  # Connection closed by the other side

            self.on_message(connection, message)

        connection.close()  # Closes this client's connection socket only

    def on_message(self, connection: socket.socket, message: bytes):
        print(f"RECEIVED MESSAGE: {message.decode()}")
        print("subclass must implement on_message method")


class CommandConnection(Connection):
    """Connection Class used for Mock Operator. This is a receiving socket class.

    Args:
        host: Host to bind the socket to usually localhost for dev
        port: Port to bind the socket to usually 8000 for dev
    """

    def on_message(self, connection: socket.socket, message: bytes):
        command_value_bytes = message[6:8]
        command_value = bytes_to_int(command_value_bytes)
        return_command_value = command_value + 0x8000
        return_command_value_bytes = int_to_bytes(
            return_command_value, num_bits=16, unsigned=True
        )
        connection.send(return_command_value_bytes)
