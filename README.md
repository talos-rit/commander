# camera_arm

Allows robot arms to be repurposed as camera arms.

## Installation

Create virtual environment and install required packages.
Using python package manager: [uv](https://docs.astral.sh/uv/getting-started/installation/)
```bash
uv sync
```
or alternatively
```bash
mkdir -p venv/py3.12
python3.12 -m venv venv/py3.12
pip install -r requirements.txt
```

**Optional Installation**
You can also opt in to install several other object detection models.

1. mediapipe
    * Run `uv sync --extra mediapipe`
    * This will add the mediapipe model options in the model dropdown menu
2. yolo
    * Run `uv sync --extra yolo`
    * This will add the yolo model option in the model dropdown menu
3. all
    * Run `uv sync --all-extras`
    * This will add all of the extra model options in the dropdown menu

## How to Run the commander

1. Main Tkinter interface
    `uv run talos.py`
2. Terminal interface
    `uv run talos.py -t` or `uv run terminal_talos.py`
3. Browser access of terminal interface*
    `uv run textual serve terminal_talos.py --host <device_ip> --port 8080`

* Install textual-serve dependency via `uv sync --group dev`

### Creating an executable
[Pyinstaller](https://pyinstaller.org/en/stable/) can be used to create an executable (on any OS) for easier launching/distribution of the application. Follow the steps below to create an executable:

>*This is especially recommended if you want to use the talos executable on a Linux machine since the executable can be upwards of 3.9 GB, making it hard for us to easily create and distribute while using the free tier of GitHub Actions.*

1. Install pyinstaller:
    
    If using uv, then the dev dependencies should be installed by default by running:
    ```bash
    uv sync --group dev
    ```
    If not using uv:
    ```bash
    pip install pyinstaller
    ```

2. Run the pyinstaller command to create an executable. This will create a `dist` folder with the executable `talos` inside.

    Using uv:
    ```bash
    uv run pyinstaller --onefile --add-data "config.yaml:." --add-data "tracking/haar_cascade/haarcascade_frontalface_default.xml:tracking/haar_cascade" --add-data "tracking/media_pipe/efficientdet_lite0.tflite:tracking/media_pipe" --add-data "tracking/media_pipe/pose_landmarker_lite.task:tracking/media_pipe" talos.py
    ```
    Otherwise:
    ```bash
    pyinstaller --onefile --add-data "config.yaml:." --add-data "tracking/haar_cascade/haarcascade_frontalface_default.xml:tracking/haar_cascade" --add-data "tracking/media_pipe/efficientdet_lite0.tflite:tracking/media_pipe" --add-data "tracking/media_pipe/pose_landmarker_lite.task:tracking/media_pipe" talos.py
    ```


## Known bugs with arm based macs
1. **Installation fails to build pybullet**
If pybullet build fails set a flag during installation:
```bash
CFLAGS="-Dfdopen=fdopen" pip install -r requirements.txt
```
or with uv
```bash
CFLAGS="-Dfdopen=fdopen" uv sync
```
2. **Tcl wasn't installed properly**
when running `uv run talos.py`, an error occurs:
`This probably means that Tcl wasn't installed properly.`.
Fix: `brew install tcl-tk` 
if this doesn't work, reinstall python for uv
`uv python uninstall 3.12 && uv python install 3.12`

## Setup

Activate your virtual environment (update 2025: no longer needed with uv)

```bash
source venv/py3.12/bin/activate
```

## Running with Operator
1. Edit `config/network_config.yaml` to set the host and port for the operator to connect to. (The Pi is unctalos.student.rit.edu:61616)
2. Turn on the robot arm and connect it to the pi via USB.
3. SSH into the Pi (username: pi, password: raspberry, IP: unctalos.student.rit.edu) and ensure the robot arm is connected by running:
```bash
    /home/pi/talos/build/bin/erv
```
4. Run the commander and it should connect to the operator. Try a home command to test the connection.


### Troubleshooting
If you are having trouble connecting to the arm, try running the following command on the Pi:
```bash
ls /dev/tty*
```
and ensure that you see a device named `/dev/ttyUSB0`
If you don't see it, try unplugging and replugging the arm and running the command again. If it still doesn't show up, try restarting the Pi.
If you see the device, but still can't connect, try running the following command on the Pi:
```bash
screen /dev/ttyUSB0 9600
```
Hit enter a few times to see if `>` shows up on each line. If it does, then the arm is connected properly. If not, try restarting the robot arm and running the command again.
After testing, exit the screen session by typing `Ctrl+A` then `K` then `Y`.
