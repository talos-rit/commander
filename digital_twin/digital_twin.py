import pybullet as p
import time

def load_robot(urdf_path):
    """
    Load a URDF robot model into the PyBullet simulation environment.
    """
    p.setAdditionalSearchPath(".")

    robot_id = p.loadURDF(urdf_path, useFixedBase=True)

    return robot_id

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
    p.setGravity(0, 0, -9.81)
    p.setRealTimeSimulation(1)

    #For this I am just making the base rotate 90 degrees in the simulation
    p.setJointMotorControl2(
        bodyIndex=robot_id,
        jointIndex=0,               #Index of the base joing
        controlMode=p.POSITION_CONTROL,
        targetPosition=1.57,        # 90 degrees in radians
        force=10
    )

    # Run the simulation
    try:
        while True:
            p.stepSimulation()
            time.sleep(1.0 / 240.0)
    except KeyboardInterrupt:
        print("Simulation terminated.")

    # Disconnect from the simulation
    p.disconnect()

# Run the main function when the script is executed
if __name__ == "__main__":
    main()
