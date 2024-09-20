import stomp

conn = stomp.Connection()
conn.connect('admin', 'admin', wait=True)
conn.send(body='Hello, world!', destination='/queue/test')
conn.disconnect()
