import socket
import struct
import time

def send_pkt(sock, cmd, payload=b''):
    hdr = struct.pack('>IH2H', 2, 0, cmd, len(payload))
    pkt = hdr + payload
    crc = 0
    for b in pkt:
        crc ^= b
    sock.sendall(pkt + struct.pack('B', crc))


def main():
    """Manual diagnostic only; running this can move or re-enable the robot."""
    with socket.create_connection(("127.0.0.1", 61616), timeout=2.0) as sock:
        sock.settimeout(2.0)
        print("Stopping any continuous movement...")
        send_pkt(sock, 0x0004)
        time.sleep(1.0)

        print("Sending CON (Enable Control)...")
        send_pkt(sock, 0x0008, struct.pack(">BI", 0x04, 0))
        time.sleep(0.5)

        print("Sending SPEED 20%...")
        send_pkt(sock, 0x0008, struct.pack(">BIB", 0x05, 0, 20))
        time.sleep(0.5)

        print("Listening for responses / telemetry...")
        start = time.time()
        while time.time() - start < 5:
            try:
                data = sock.recv(1024)
                if data:
                    print("RECV:", repr(data))
            except socket.timeout:
                pass


if __name__ == "__main__":
    main()
