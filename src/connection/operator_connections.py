import socket
import threading
import time

from loguru import logger

from src.icd_config import CTypesInt, toBytes, toInt


class OperatorConnection:
    """Base Connection Class, Creates Socket connection on initialization."""

    is_running = False
    command_count = 0
    thread: threading.Thread | None = None
    _term: int | None = None

    def __init__(self, host, port, connect_on_init=True):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if connect_on_init:
            # Start connection on a separate thread so it doesn't block
            self.connect_on_thread()

    def connect_on_thread(self):
        self.thread = threading.Thread(target=self.connect, daemon=True)
        self.thread.start()

    def connect(self):
        self.is_running = True
        for attempt in range(5):
            if not self.is_running:
                return  # Exit since this connection is not needed anymore
            try:
                self.socket.connect((self.host, self.port))
                logger.debug(f"Connected to socket: {self.host}:{self.port}")
                break
            except OSError as e:
                logger.error(
                    f"[Connection]: Bind failed, retrying in 5s({attempt + 1}/5) {e}"
                )
                time.sleep(5)
        else:
            return  # Failed to connect after retries

    def close(self):
        """Cleanly close the socket port and stop listening to new connections."""
        self.is_running = False
        if self.thread is not None:
            self.thread.join()
        self.socket.close()
        logger.debug(f"Socket closed cleanly {self.host}:{self.port}")

    def xor_checksum(self, data: bytes) -> int:
        result = 0
        for byte in data:
            result ^= byte
        return result

    def publish(self, command: int, payload: bytes | None = None):
        """
        Command ID      UINT32	Unique ID for individual commands
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        RESERVED     	UINT16	RESERVED
        Command Value	UINT16	Command for device to carry out
        Length	        UINT16	Length of Payload
        Payload	        UINT8[]	Command Info
        CRC	            UINT8	Checksum
        """
        # Get a unique, incrementing command id. Increment by 2, so that the response
        # from the operator always returns odd command ids and the publisher always sends
        # even command ids. Commands can be associated with each other by checking if they
        # have the same modulus of 2.
        command_id = self.command_count
        self.command_count += 2
        payload_length = 0 if payload is None else len(payload)

        command_id = toBytes(command_id, CTypesInt.UINT32)
        reserved = toBytes(0, CTypesInt.UINT16)
        command_byte = toBytes(command, CTypesInt.UINT16)
        payload_length = toBytes(payload_length, CTypesInt.UINT16)

        # Put header together
        header = command_id + reserved + command_byte + payload_length

        # Put everything together
        message = header

        if payload is not None:
            message += payload

        crc_value = self.xor_checksum(message)
        crc = toBytes(crc_value, CTypesInt.UINT8)

        message += crc

        try:
            self.socket.sendall(message)  # safer than send()
        except OSError as e:
            logger.error(f"Socket send to {self.host} failed: {e}")
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
        logger.info(f"RECEIVED MESSAGE: {message.decode()}")
        logger.info("subclass must implement on_message method")


class CommandConnection(OperatorConnection):
    """Connection Class used for Mock Operator. This is a receiving socket class.

    Args:
        host: Host to bind the socket to usually localhost for dev
        port: Port to bind the socket to usually 8000 for dev
    """

    def on_message(self, connection: socket.socket, message: bytes):
        command_value_bytes = message[6:8]
        command_value = toInt(command_value_bytes)
        return_command_value = command_value + 0x8000
        return_command_value_bytes = toBytes(return_command_value, CTypesInt.UINT16)
        connection.send(return_command_value_bytes)

    def connect(self):
        self.is_running = True
        for attempt in range(5):
            if not self.is_running:
                return  # Exit since this connection is not needed anymore
            try:
                self.socket.bind((self.host, self.port))
                logger.debug(f"Bound to socket: {self.host}:{self.port}")
                break
            except OSError as e:
                logger.error(
                    f"[Connection]: Bind failed, retrying in 5s({attempt + 1}/5) {e}"
                )
                time.sleep(5)
        else:
            return  # Failed to bind after retries

        logger.debug("Starting to listen!")
        self.socket.listen()
        while self.is_running:
            try:
                connection, address = self.socket.accept()
                logger.debug(f"Got connection from {address}")
                self.listen(connection)
            except OSError as e:
                logger.error(f"OS Error: {e}")
                break
