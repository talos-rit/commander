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
