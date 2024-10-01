import stomp


INSTRUCTIONS_DESTINATION = 'queue/instructions'


class Connection:
    def __init__(self):
        self.connection = stomp.Connection()
        self.connection.connect('admin', 'admin', wait=True)

    def publish(self, body, destination):
        self.connection.send(body=body, destination=destination)


class Publisher:
    connection = Connection()

    @staticmethod
    def move(x, y, z):
        # Placeholder message
        Publisher.connection.publish(f'Move to {x}, {y}, {z}', destination=INSTRUCTIONS_DESTINATION)

    @staticmethod
    def rotate(deg):
        # Placeholder message
        Publisher.connection.publish(f'Rotate {deg}', destination=INSTRUCTIONS_DESTINATION)

