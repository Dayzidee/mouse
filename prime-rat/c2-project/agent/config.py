import configparser
import os

# --- Path Configuration ---
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_BASE_DIR, 'agent_config.ini')

# Read the configuration file
config = configparser.ConfigParser()
config.read(_CONFIG_PATH)

# --- Connection Settings ---
SERVER_HOST = config.get('Connection', 'host', fallback='127.0.0.1')
SERVER_PORT = config.getint('Connection', 'port', fallback=6666)
RECONNECT_DELAY = config.getint('Connection', 'reconnect_delay_seconds', fallback=10)
# --- FIX: Add path to the server's certificate for verification ---
CERTFILE = os.path.join(_BASE_DIR, config.get('Connection', 'certfile', fallback='server.crt'))