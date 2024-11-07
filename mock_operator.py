import stomp
import time
from publisher import INSTRUCTIONS_DESTINATION

class MyListener(stomp.ConnectionListener):
    def on_error(self, frame):
        print('received an error "%s"' % frame.body)

    def on_message(self, frame):
        print('received a message "%s"' % bytes(frame.body, 'utf-8'))

conn = stomp.Connection()
conn.set_listener(name='My listener', listener=MyListener())
conn.connect('admin', 'admin', wait=True)
conn.subscribe(destination=INSTRUCTIONS_DESTINATION, id=1)
time.sleep(10)
conn.disconnect()
