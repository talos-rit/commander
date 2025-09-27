from utils import load_config

# Publisher
SOCKET_HOST = "operator.talos"
# SOCKET_HOST = "localhost"
SOCKET_PORT = 61616

CAMERA_CONFIG = load_config("./config.yaml")
