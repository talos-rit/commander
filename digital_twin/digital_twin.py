import math
import struct
import time

import pybullet as pyblt
import stomp
from stomp.utils import encode

# DEPRECATED


class MyListener(stomp.ConnectionListener):
    AZIMUTH_JOIN_INDEX = 0
    ALTITUDE_JOIN_INDEX = 3

    def __init__(self, robot_id):
        self.robot_id = robot_id

    def on_message(self, frame):
        """
        This method is called whenever the listener receives a message from active mq.
        Right now it only works for polar pan, it parses the message and calls
        delta azimuth or delta altitude.
        """
        message = encode(frame.body, encoding="utf-8")

        command_id, reserved, command, payload_length = struct.unpack(
            ">I H H H", message[:10]
        )

        delta_azimuth, delta_altitude, delay, duration = struct.unpack(
            ">iiII", message[10:26]
        )

        print("Command ID:", command_id)
        print("Reserved:", reserved)
        print("Command:", command)
        print("Payload Length:", payload_length)
        print("Delta Azimuth:", delta_azimuth)
        print("Delta Altitude:", delta_altitude)
        print("Delay:", delay)
        print("Duration:", duration)

        if delta_azimuth != 0:
            self.rotate_azimuth(delta_azimuth)
        if delta_altitude != 0:
            self.rotate_altitude(delta_altitude)

    def rotate_azimuth(self, deg):
        """
        Method to rotate the base of the digital twin
        """
        joint_index = self.AZIMUTH_JOIN_INDEX  # Azimuth joint index
        current_angle = pyblt.getJointState(self.robot_id, joint_index)[0]
        new_angle = current_angle + math.radians(deg)  # Convert degrees to radians
        pyblt.resetJointState(self.robot_id, joint_index, new_angle)
        pyblt.stepSimulation()
        print(f"Rotated azimuth by {deg} degrees.")

    def rotate_altitude(self, deg):
        joint_index = self.ALTITUDE_JOIN_INDEX  # Altitude joint index
        current_angle = pyblt.getJointState(self.robot_id, joint_index)[0]
        new_angle = current_angle + math.radians(deg)  # Convert degrees to radians
        pyblt.resetJointState(self.robot_id, joint_index, new_angle)
        pyblt.stepSimulation()
        print(f"Rotated altitude by {deg} degrees.")


def load_robot(urdf_path):
    """
    Load a URDF robot model into the PyBullet simulation environment.
    """
    pyblt.setAdditionalSearchPath(".")

    robot_id = pyblt.loadURDF(urdf_path, useFixedBase=True)

    return robot_id


def setup_active_mq_listener(robot_id):
    """
    Set up the ActiveMQ connection and listener for receiving movement commands.
    """
    conn = stomp.Connection(auto_decode=False)  # [('localhost', 8161)]
    listener = MyListener(robot_id)
    conn.set_listener("", listener)
    conn.connect(
        "admin", "admin", wait=True
    )  # Replace with ActiveMQ username and password
    conn.subscribe(destination="/queue/instructions", id=1, ack="auto")

    return conn


def main():
    # Start PyBullet in GUI mode
    physics_client = pyblt.connect(pyblt.GUI)

    # Path to the URDF file
    urdf_path = "sboter4u_model/robots/sboter4u_model.urdf"

    # Load the URDF file
    robot_id = load_robot(urdf_path)

    # Get joint information
    num_joints = pyblt.getNumJoints(robot_id)
    for i in range(num_joints):
        joint_info = pyblt.getJointInfo(robot_id, i)
        print(f"Joint {i}: {joint_info[1].decode('utf-8')}")

    # Set gravity and enable real-time simulation
    pyblt.setGravity(0, 0, 0)
    pyblt.setRealTimeSimulation(1)

    BSEPRhome = [0.00000, -2.09925, 1.65843, 1.54994, 0.00000]

    # Set up the ActiveMQ listener
    conn = setup_active_mq_listener(robot_id)

    # Set each joint to the home position
    for joint_index, angle in enumerate(BSEPRhome):
        pyblt.resetJointState(robot_id, joint_index, angle)
        pyblt.stepSimulation()

        # This is to set the gripper to be pointing straight ahead
        new_angle = 1.54994 - math.radians(65)
        pyblt.resetJointState(robot_id, 3, new_angle)
        pyblt.stepSimulation()

    # Run the simulation and keep listening for ActiveMQ commands
    try:
        while True:
            pyblt.stepSimulation()
            time.sleep(1.0 / 240.0)  # Adjust the simulation speed
    except KeyboardInterrupt:
        print("Simulation terminated.")
    finally:
        pyblt.disconnect()
        conn.disconnect()


# Run the main function when the script is executed
if __name__ == "__main__":
    main()
