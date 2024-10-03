import stomp


INSTRUCTIONS_DESTINATION = '/queue/instructions'


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
        self.connection.send(body=body, destination=destination)


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

