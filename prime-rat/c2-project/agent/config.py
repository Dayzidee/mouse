import configparser

# Read the configuration file
config = configparser.ConfigParser()
config.read('agent/agent_config.ini')

# --- Connection Settings ---
SERVER_HOST = config.get('Connection', 'host', fallback='127.0.0.1')
SERVER_PORT = config.getint('Connection', 'port', fallback=6666)
RECONNECT_DELAY = config.getint('Connection', 'reconnect_delay_seconds', fallback=10)