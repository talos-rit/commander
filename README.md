# camera_arm

Allows robot arms to be repurposed as camera arms.

## Installation

Install ActiveMQ

bash:

```bash
brew install apache-activemq
```

Create virtual environment and install required packages.

```bash
mkdir -p venv/py3.12
python3.12 -m venv venv/py3.12
pip install -r requirements.txt
```

## Setup

Start the ActiveMQ service

bash:

```bash
brew services start activemq
```

Then, navigate to the ActiveMQ dashboard hosted at
[http://localhost:8161/admin](http://localhost:8161/admin)

Activate your virtual environment

```bash
source venv/py3.12/bin/activate
```
