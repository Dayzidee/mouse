import configparser
import os

# --- Path Configuration ---
# Get the absolute path of the directory this config.py file is in.
# This makes all other paths relative to this file, which is robust.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_BASE_DIR, 'server_config.ini')

# Read the configuration file using its absolute path
config = configparser.ConfigParser()
config.read(_CONFIG_PATH)

# --- Server Settings ---
HOST = config.get('Server', 'host', fallback='0.0.0.0')
PORT = config.getint('Server', 'port', fallback=6666)

# --- Certificate Paths (Now Resolved Correctly) ---
CERTFILE = os.path.join(_BASE_DIR, config.get('Server', 'certfile', fallback='server.crt'))
KEYFILE = os.path.join(_BASE_DIR, config.get('Server', 'keyfile', fallback='server.key'))

# --- Logging Settings ---
LOG_FILE = os.path.join(_BASE_DIR, config.get('Server', 'log_file', fallback='server_activity.log'))
LOG_LEVEL = config.get('Server', 'log_level', fallback='INFO')

# --- Behaviour Settings ---
COMMAND_TIMEOUT = config.getint('Behaviour', 'command_timeout_seconds', fallback=15)