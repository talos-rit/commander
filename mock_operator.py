import stomp
import time

class MyListener(stomp.ConnectionListener):
    def on_error(self, frame):
        print('received an error "%s"' % frame.body)

    def on_message(self, frame):
        print('received a message "%s"' % frame.body)

conn = stomp.Connection()
conn.set_listener(name='My listener', listener=MyListener())
conn.connect('admin', 'admin', wait=True)
conn.subscribe(destination='/queue/test', id=1)
time.sleep(10)
conn.disconnect()
