from icd_config import int_to_bytes, bytes_to_int
import socket
import time
import threading


class Connection:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_connected = False
        self.async_connect()
        self.command_count = 0

    def async_connect(self):
        thread = threading.Thread(target=self.connect)
        thread.start()

    def connect(self):
        raise NotImplementedError("connect method is not implemented")

    def close_socket(self):
        self.socket.close()
        self.is_connected = False

    def publish(self, command: int, payload: bytes = None):
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

        if payload != None:
            payload_length = len(payload)
        else:
            payload_length = 0

        # TODO: Implement checksum. May get removed
        crc = int_to_bytes(0, num_bits=16, unsigned=True)

        command_id = int_to_bytes(command_id, num_bits=32, unsigned=True)
        reserved = int_to_bytes(0, num_bits=16, unsigned=True)
        command = int_to_bytes(command, num_bits=16, unsigned=True)
        payload_length = int_to_bytes(payload_length, num_bits=16, unsigned=True)

        # Put header together
        header = command_id + reserved + command + payload_length

        # Put everything together 
        body = header

        if payload != None:
            body += payload

        body += crc

        self.socket.send(body)
        response = self.socket.recv(2048)
        return response


class OperatorConnection(Connection):
    def connect(self):
        while(True):
            try:
                self.socket.connect((self.host, self.port))
                self.is_connected = True
                print("Connected to socket: " + self.host + ":" + str(self.port))
                break
            except ConnectionRefusedError: # catch refused connection for retry
                print("Connection to " + self.host + ":" + str(self.port) + " failed, retrying in 5s")
                time.sleep(5)


# The following code is used for the Mock Operator
class CommandConnection(Connection):
    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        while(True):
            try:
                self.socket.bind((self.host, self.port))
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
            self.is_connected = True
            print ('Got connection from', address)
            thread = threading.Thread(target=self.listen, args=(connection,))
            thread.start()

    def listen(self, connection):
        while True:
            message = connection.recv(2048)

            if len(message) == 0:
                continue

            print(f"RECEIVED MESSAGE: {message}")
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
