# Commander
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/talos-rit/commander)

Allows robot arms to be repurposed as camera arms.
Python application that tracks a subject using a camera feed, interprets the subject's position, and sends commands to a robot arm to move a camera accordingly.

## Installation

Create virtual environment and install required packages.
Using python package manager: [uv](https://docs.astral.sh/uv/getting-started/installation/)
```bash
uv sync
```
or alternatively
```bash
mkdir -p .venv/py3.12
python3.12 -m venv .venv/py3.12
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

## Setting up the virtual camera
In order to stream video out of commander, you will need to set up a virtual camera on your computer. This will allow you to select the commander video stream as a camera input in other applications (e.g. zoom, obs, etc.). Please refer to the pyvirtualcam documentation for instructions on how to set up a virtual camera on your operating system: https://github.com/letmaik/pyvirtualcam.
**Note: If you are on MacOS or Windows the default backend for pyvirtualcam is obs while v4l2 is the default for Linux. If you want to use the obs backend on MacOS or Windows, you will need to have obs installed and running. Refer to pyvirtualcam's documentation for additional setup instructions. If you want to use the v4l2 backend on Linux, you will need to have v4l2loopback installed and set up.**

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
    uv run pyinstaller_runner.py
    ```
    Otherwise:
    ```bash
    python pyinstaller_runner.py
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

## Running

Using uv, run the general app entry point:
```bash
uv run commander
```

Run the TUI interface:
```bash
uv run commander-terminal
```
or
```bash
uv run commander -t
```

Run the Tk GUI interface:
```bash
uv run commander-tk
```

## Configurations
The `config/example_default_config.yaml` file contains default parameters for the application that will be used to fill in the new connections configs. You can override these parameters using `config/default_config.local.yaml` which will be prioritized over the example default config. 

When you create a new connection in the commander application, it will automatically create a new config file, `config/robot_configs.local.yaml`. This file will contain the parameters for each connection you create. You can also edit this file directly to change the parameters for each connection.

### App settings overrides
`AppSettings` are loaded from `config/app_settings.local.yaml`, and can be overridden by environment variables.

Priority order:
1. Environment variables (including `.env`)
2. `config/app_settings.local.yaml`
3. Hardcoded defaults in the schema

Supported environment variables:
- `COMMANDER_LOG_LEVEL`
- `COMMANDER_BBOX_MAX_FPS`
- `COMMANDER_FRAME_PROCESS_FPS`

Example:
```bash
export COMMANDER_BBOX_MAX_FPS=15
uv run commander
```


## Running Tests
To run the tests, use the following command. By default, this command will run both unit and integration tests and generate a coverage report:
```bash
uv run pytest
```
To run only unit tests:
```bash
uv run pytest tests/unit/
```
To run only integration tests:
```bash
uv run pytest tests/integration/
```

## Static Analysis
To run static analysis using sonarqube locally, you can use the provided docker-compose file to set up a SonarQube instance. The following steps outline how to setup your environment so that you can run SonarQube properly.

1. Make sure you have docker and docker-compose installed on your machine.

2. Setup the .env file
```bash
cp .env.example .env
```
Then update the values in the .env file as needed. The default values should work for most cases, but you can change the `SONAR_NEW_PASS` value to something more secure if you plan on using this in a production environment.

3. Configure proper permissions:
```bash
sudo chown -R 1000:1000 .
```

4. Create the xml reports for coverage and test results by running the following command:
```bash
uv run pytest --cov-report=xml:coverage.xml --junitxml=pytest_report.xml
```

5. Run the following command in the root directory of the project:
```bash
docker-compose -f docker-compose.sonarqube.yml up -d
```

6. See the results.
```bash
visit http://localhost:9888 in the browser
login with the credentials from .env
```

7. If you want to run the analysis again after making changes, make sure to regenerate the xml reports by running the command in step 4 again, then run the following command to trigger a new analysis:
```bash
docker compose -f docker-compose.sonarqube.yml run --rm sonarscanner
```

You can use `docker-compose -f docker-compose.sonarqube.yml down` to stop the SonarQube instance when you are done.

## Troubleshooting
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
