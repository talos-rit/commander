"""
Client for the Operator C++ service on the Raspberry Pi.
Implements the ICD binary packet protocol and parses asynchronous telemetry (TELP / TEL).
"""

import socket
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional
from loguru import logger
try:
    from .operator_faults import OperatorFaultLog
except ImportError:
    from operator_faults import OperatorFaultLog


# ICD Command IDs from commander/src/icd_config.py
class ICDCommand:
    HANDSHAKE = 0x0000
    HANDSHAKE_RETURN = 0x8000
    POLAR_PAN_DISCRETE = 0x0001
    POLAR_PAN_DISCRETE_RETURN = 0x8001
    HOME = 0x0002
    HOME_RETURN = 0x8002
    POLAR_PAN_CONTINUOUS_START = 0x0003
    POLAR_PAN_CONTINUOUS_START_RETURN = 0x8003
    POLAR_PAN_CONTINUOUS_STOP = 0x0004
    POLAR_PAN_CONTINUOUS_STOP_RETURN = 0x8004
    EXECUTE_HARDWARE_OPERATION = 0x0008
    EXECUTE_HARDWARE_OPERATION_RETURN = 0x8008
    SET_SPEED = 0x000A
    SET_SPEED_RETURN = 0x800A


@dataclass
class RobotTelemetry:
    base: int = 0
    shoulder: int = 0
    elbow: int = 0
    wrist_pitch: int = 0
    wrist_roll: int = 0
    last_updated_monotonic: float = 0.0
    has_received: bool = False

    def is_fresh(self, max_age_s: float, now: Optional[float] = None) -> bool:
        if not self.has_received:
            return False
        current = time.monotonic() if now is None else now
        return current - self.last_updated_monotonic <= max_age_s


class OperatorClient:
    """Thread-safe TCP client for sending ICD commands to Operator and receiving telemetry."""

    def __init__(self, host: str = "127.0.0.1", port: int = 61616, auto_connect: bool = True):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.is_running = False
        self.is_connected = False
        self.command_counter = 0
        self._send_lock = threading.RLock()
        self._telemetry_lock = threading.Lock()
        self.telemetry = RobotTelemetry()
        self._recv_thread: Optional[threading.Thread] = None
        self._message_listeners: list[Callable[[str], None]] = []
        self._fault_lock = threading.Lock()
        self._fault_message: Optional[str] = None
        self._fault_log = OperatorFaultLog()
        self._fault_thread = None

        if auto_connect:
            self.start()

    def start(self):
        """Starts the background connection and receiver thread."""
        if self.is_running:
            return
        self.is_running = True
        self._recv_thread = threading.Thread(target=self._connection_loop, daemon=True, name="OperatorClientThread")
        self._recv_thread.start()
        if self.host in ("127.0.0.1", "localhost", "::1"):
            self._fault_thread = threading.Thread(target=self._watch_fault_log, daemon=True, name="OperatorFaultLog")
            self._fault_thread.start()

    def _watch_fault_log(self):
        while self.is_running:
            for fault in self._fault_log.poll():
                self._handle_telemetry_line("FAULT " + fault)
            time.sleep(.25)

    def stop(self):
        """Closes connection and stops thread."""
        self.is_running = False
        self._disconnect()
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=1.0)

    def _disconnect(self):
        self.is_connected = False
        with self._send_lock:
            if self.socket:
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    self.socket.close()
                except OSError:
                    pass
                self.socket = None

    def _connection_loop(self):
        """Monitors and maintains connection to Operator with auto-reconnect."""
        while self.is_running:
            if not self.is_connected:
                try:
                    logger.info(f"[OperatorClient] Connecting to Operator at {self.host}:{self.port}...")
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(3.0)
                    s.connect((self.host, self.port))
                    s.settimeout(1.0)
                    self.socket = s
                    self.is_connected = True
                    logger.info(f"[OperatorClient] Successfully connected to Operator at {self.host}:{self.port}")
                except (OSError, socket.error) as e:
                    logger.debug(f"[OperatorClient] Connection to Operator failed: {e}. Retrying in 2s...")
                    time.sleep(2.0)
                    continue

            # Read telemetry from socket
            buffer = b""
            while self.is_running and self.is_connected:
                try:
                    chunk = self.socket.recv(1024)
                    if not chunk:
                        logger.warning("[OperatorClient] Operator closed the socket connection.")
                        self._disconnect()
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        decoded = line.decode(errors="replace").strip()
                        if decoded:
                            self._handle_telemetry_line(decoded)
                except socket.timeout:
                    continue
                except OSError as e:
                    if self.is_running:
                        logger.warning(f"[OperatorClient] Socket recv error: {e}")
                    self._disconnect()
                    break

            time.sleep(1.0)

    def _handle_telemetry_line(self, line: str):
        """Parses TELP or TEL messages from Operator."""
        cleaned = line.replace("\x00", " ").strip()
        parts = cleaned.split()
        if not parts:
            return

        if parts[0] in ("TELP", "TEL") and len(parts) >= 6:
            try:
                base, shoulder, elbow, wrist_pitch, wrist_roll = (int(p) for p in parts[1:6])
                with self._telemetry_lock:
                    self.telemetry = RobotTelemetry(
                        base=base,
                        shoulder=shoulder,
                        elbow=elbow,
                        wrist_pitch=wrist_pitch,
                        wrist_roll=wrist_roll,
                        last_updated_monotonic=time.monotonic(),
                        has_received=True,
                    )
            except ValueError:
                pass
        elif any(k in cleaned.upper() for k in ("IMPACT", "DISABLED", "FAULT", "ERROR", "NOT FOUND")):
            with self._fault_lock:
                self._fault_message = cleaned
            logger.warning(f"[OperatorClient] Latched Scorbot fault: '{cleaned}'")

        for listener in tuple(self._message_listeners):
            try:
                listener(line)
            except Exception as e:
                logger.error(f"[OperatorClient] Listener error: {e}")

    def get_telemetry(self) -> RobotTelemetry:
        """Thread-safe snapshot of latest telemetry."""
        with self._telemetry_lock:
            return RobotTelemetry(
                base=self.telemetry.base,
                shoulder=self.telemetry.shoulder,
                elbow=self.telemetry.elbow,
                wrist_pitch=self.telemetry.wrist_pitch,
                wrist_roll=self.telemetry.wrist_roll,
                last_updated_monotonic=self.telemetry.last_updated_monotonic,
                has_received=self.telemetry.has_received,
            )

    def add_telemetry_listener(self, callback: Callable[[str], None]):
        self._message_listeners.append(callback)

    def get_fault(self) -> Optional[str]:
        with self._fault_lock:
            return self._fault_message

    def clear_fault(self) -> bool:
        """Explicitly request CON once and clear the local latch if dispatched."""
        sent = self.erv_enable_control()
        if sent:
            with self._fault_lock:
                self._fault_message = None
        return sent

    @staticmethod
    def _xor_checksum(data: bytes) -> int:
        crc = 0
        for b in data:
            crc ^= b
        return crc

    def send_command(self, command_id: int, payload: bytes = b"") -> bool:
        """Builds and sends an ICD packet to Operator."""
        if not self.is_connected or not self.socket:
            logger.warning(f"[OperatorClient] Cannot send command {hex(command_id)}: Not connected to Operator.")
            return False

        with self._send_lock:
            self.command_counter = (self.command_counter + 2) & 0xFFFFFFFF
            cmd_id_val = self.command_counter
            reserved = 0
            payload_len = len(payload)

            header = struct.pack(">IH2H", cmd_id_val, reserved, command_id, payload_len)
            packet = header + payload
            crc = self._xor_checksum(packet)
            packet += struct.pack("B", crc)

            try:
                self.socket.sendall(packet)
                return True
            except OSError as e:
                logger.error(f"[OperatorClient] Send failed: {e}")
                self._disconnect()
                return False

    # Convenience motion commands
    def polar_pan_continuous_start(self, moving_azimuth: int = 0, moving_altitude: int = 0) -> bool:
        """
        Starts or updates continuous polar pan.
        moving_azimuth: -1 (clockwise/left), 0 (none), 1 (counter-clockwise/right)
        moving_altitude: -1 (down), 0 (none), 1 (up)
        """
        payload = struct.pack("bb", int(moving_azimuth), int(moving_altitude))
        return self.send_command(ICDCommand.POLAR_PAN_CONTINUOUS_START, payload)

    def tracking_jog_start(self, azimuth: int, altitude: int, interval_ms: int) -> bool:
        """Set Pi-local tracking direction and serial jog cadence without exiting manual mode."""
        return self.execute_hardware_operation(0x06, struct.pack("bbB", azimuth, altitude, interval_ms))

    def polar_pan_continuous_stop(self) -> bool:
        """Stops continuous polar pan movement."""
        return self.send_command(ICDCommand.POLAR_PAN_CONTINUOUS_STOP, b"")

    def polar_pan_discrete(self, delta_azimuth: int, delta_altitude: int, delay_ms: int = 0, duration_ms: int = 250) -> bool:
        """Executes a discrete polar pan movement."""
        payload = struct.pack(">iiII", delta_azimuth, delta_altitude, delay_ms, duration_ms)
        return self.send_command(ICDCommand.POLAR_PAN_DISCRETE, payload)

    def execute_hardware_operation(self, subcommand: int, payload: bytes = b"") -> bool:
        """
        Hardware operation packet:
        Subcommand (uint8) + reserved (uint32) + payload (bytes)
        """
        body = struct.pack(">BI", subcommand, 0) + payload
        return self.send_command(ICDCommand.EXECUTE_HARDWARE_OPERATION, body)

    def erv_enable_control(self) -> bool:
        """Request ACL 'CON' to clear faults and re-enable ER-V servo control."""
        logger.info("[OperatorClient] Sending ER-V Enable Control (CON)...")
        return self.execute_hardware_operation(0x04, b"")

    def erv_set_speed_percent(self, percent: int = 20) -> bool:
        """Request ACL 'SPEED n' for ER-V 1..100% speed setting."""
        val = max(1, min(100, percent))
        logger.info(f"[OperatorClient] Setting ER-V Speed to {val}%...")
        return self.execute_hardware_operation(0x05, struct.pack("B", val))

    def home(self, delay_ms: int = 0) -> bool:
        payload = struct.pack(">I", delay_ms)
        return self.send_command(ICDCommand.HOME, payload)

    def set_speed(self, speed: int) -> bool:
        return self.erv_set_speed_percent(speed)
