# camera_arm

Allows robot arms to be repurposed as camera arms.

## Installation

Install ActiveMQ

bash:

```bash
brew install apache-activemq
```

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

### Creating an executable
[Pyinstaller](https://pyinstaller.org/en/stable/) can be used to create an executable (on any OS) for easier launching/distribution of the application. Follow the steps below to create an executable:

>*This is especially recommended if you want to use the talos executable on a Linux machine since the executable can be upwards of 3.9 GB, making it hard for us to easily create and distribute while using the free tier of GitHub Actions.*

1. Install pyinstaller:
    
    If using uv, then the dev dependencies should be installed by default by running:
    ```bash
    uv sync
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

Start the ActiveMQ service

bash:

```bash
brew services start activemq
```

Then, navigate to the ActiveMQ dashboard hosted at
[http://localhost:8161/admin](http://localhost:8161/admin)

Activate your virtual environment (update 2025: no longer needed with uv)

```bash
source venv/py3.12/bin/activate
```
