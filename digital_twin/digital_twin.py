import pybullet as p
import stomp
import time
import math

class MyListener(stomp.ConnectionListener):
    def __init__(self, robot_id):
        self.robot_id = robot_id

    def on_message(self, frame):
        message = frame.body

        # Parse the message and execute corresponding action
        if "Rotate azimuth" in message:
            deg = float(message.split(' ')[-1])  # Extract degree value
            self.rotate_azimuth(deg)
        elif "Rotate altitude" in message:
            deg = float(message.split(' ')[-1])  # Extract degree value
            self.rotate_altitude(deg)

    def rotate_azimuth(self, deg):
        joint_index = 0  # Azimuth joint index
        current_angle = p.getJointState(self.robot_id, joint_index)[0]
        new_angle = current_angle + math.radians(deg)  # Convert degrees to radians
        p.resetJointState(self.robot_id, joint_index, new_angle)
        p.stepSimulation()
        print(f"Rotated azimuth by {deg} degrees.")

    def rotate_altitude(self, deg):
        joint_index = 3  # Altitude joint index
        current_angle = p.getJointState(self.robot_id, joint_index)[0]
        new_angle = current_angle + math.radians(deg)  # Convert degrees to radians
        p.resetJointState(self.robot_id, joint_index, new_angle)
        p.stepSimulation()
        print(f"Rotated altitude by {deg} degrees.")

def load_robot(urdf_path):
    """
    Load a URDF robot model into the PyBullet simulation environment.
    """
    p.setAdditionalSearchPath(".")

    robot_id = p.loadURDF(urdf_path, useFixedBase=True)

    return robot_id

def setup_active_mq_listener(robot_id):
    """
    Set up the ActiveMQ connection and listener for receiving movement commands.
    """
    conn = stomp.Connection()  # [('localhost', 8161)]
    listener = MyListener(robot_id)
    conn.set_listener('', listener)
    conn.connect('admin', 'admin', wait=True)  # Replace with ActiveMQ username and password
    conn.subscribe(destination='/queue/instructions', id=1, ack='auto')

    return conn

def main():
    # Start PyBullet in GUI mode
    physics_client = p.connect(p.GUI)

    # Path to the URDF file
    urdf_path = "sboter4u_model/robots/sboter4u_model.urdf"

    # Load the URDF file
    robot_id = load_robot(urdf_path)

    # Get joint information
    num_joints = p.getNumJoints(robot_id)
    for i in range(num_joints):
        joint_info = p.getJointInfo(robot_id, i)
        print(f"Joint {i}: {joint_info[1].decode('utf-8')}") 

    # Set gravity and enable real-time simulation
    p.setGravity(0, 0, 0)
    p.setRealTimeSimulation(1)


    BSEPRhome = [0.00000, -2.09925, 1.65843, 1.54994, 0.00000]

    # Set each joint to the home position
    for joint_index, angle in enumerate(BSEPRhome):
        p.resetJointState(robot_id, joint_index, angle)
        p.stepSimulation()

        #This is to set the gripper to be pointing straight ahead
        new_angle = 1.54994 - math.radians(65)
        p.resetJointState(robot_id, 3, new_angle)
        p.stepSimulation()


    # angle_increment = 0.5  # This can be adjusted as needed (e.g., move to 0.5 radians)
    # hold_time = 1  # How long to hold each position in seconds

    # for joint_index in range(5):

    #     current_angle = p.getJointState(robot_id, joint_index)[0]
    #     new_angle = current_angle + angle_increment

    #     # Set the joint to the new angle
    #     p.resetJointState(robot_id, joint_index, new_angle)

    #     # Step the simulation for a certain duration
    #     start_time = time.time()
    #     while time.time() - start_time < hold_time:
    #         p.stepSimulation()
    #         time.sleep(1.0 / 240.0)  # Adjust as needed to control simulation speed


    #     current_angle = p.getJointState(robot_id, joint_index)[0]
    #     new_angle = current_angle - angle_increment

    #     # Set the joint to the new angle
    #     p.resetJointState(robot_id, joint_index, new_angle)

    #     # Step the simulation to move the joint back
    #     start_time = time.time()
    #     while time.time() - start_time < hold_time:
    #         p.stepSimulation()
    #         time.sleep(1.0 / 240.0)


    # Set up the ActiveMQ listener
    conn = setup_active_mq_listener(robot_id)

    # Run the simulation and keep listening for ActiveMQ commands
    try:
        while True:
            p.stepSimulation()
            time.sleep(1.0 / 240.0)  # Adjust the simulation speed
    except KeyboardInterrupt:
        print("Simulation terminated.")
    finally:
        p.disconnect()
        conn.disconnect()

# Run the main function when the script is executed
if __name__ == "__main__":
    main()
