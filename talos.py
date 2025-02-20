from manual_interface import ManualInterface

def main():

    while (not Publisher.connection.is_connected):
        print("Waiting to connect...")
        time.sleep(5)
  
    interface = ManualInterface()
    interface.launch_user_interface()  


if __name__ == "__main__":
    main()
