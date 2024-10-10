import stomp


INSTRUCTIONS_DESTINATION = '/queue/TEST.FOO'


class Connection:
    """
    The publisher class does not have an initialization since it is a static class.
    This class exists to initialize a single connection instance that is used by the
    publisher. Also contains a function that is used to publish messages.
    """
    def __init__(self):
        self.connection = stomp.Connection()
        self.connection.connect('admin', 'admin', wait=True)

    def publish(self, body, destination):
        """
        Recipient: UINT16
        Sender: UINT16
        Command: UINT16
        Length: UINT16
        Payload: UINT8[]
        CRC: UINT16
        """
        my_byte_array = bytearray([1, 2, 3, 4])
        my_bytes = b"" + my_byte_array
        self.connection.send(body=my_bytes, destination=destination, content_type="text")


class Publisher:
    """
    A static class that is used to publish instructions to the operator.
    """
    connection = Connection()

    @staticmethod
    def move(x, y, z):
        # Placeholder message
        Publisher.connection.publish(f'Move to {x}, {y}, {z}', destination=INSTRUCTIONS_DESTINATION)

    @staticmethod
    def rotate(deg):
        # Placeholder message
        Publisher.connection.publish(f'Rotate {deg}', destination=INSTRUCTIONS_DESTINATION)

