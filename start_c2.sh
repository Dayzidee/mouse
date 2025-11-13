#!/bin/bash

# Define paths relative to the script's location
SCRIPT_DIR=$(dirname "$0")
SERVER_DIR="$SCRIPT_DIR/prime-rat/c2-project/server"
AGENT_DIR="$SCRIPT_DIR/prime-rat/c2-project/agent"
SERVER_MAIN="$SERVER_DIR/main_server.py"
AGENT_MAIN="$AGENT_DIR/main_agent.py"
CERT_FILE="$SERVER_DIR/server.crt"
KEY_FILE="$SERVER_DIR/server.key"

# 1. Check for certificates
echo "[*] Checking for SSL certificates..."
if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "[!] ERROR: SSL certificates (server.crt, server.key) not found in $SERVER_DIR."
    echo "[!] Please generate them before starting the C2 server."
    exit 1
fi
echo "[+] Certificates found."

# 2. Launch the server in the background
echo "[*] Starting the C2 server in the background..."
python3 "$SERVER_MAIN" > "$SCRIPT_DIR/server.log" 2>&1 &
SERVER_PID=$!
echo "[+] Server started with PID: $SERVER_PID. Log: $SCRIPT_DIR/server.log"

# 3. Launch the agent in the background
echo "[*] Starting the C2 agent in the background..."
python3 "$AGENT_MAIN" > "$SCRIPT_DIR/agent.log" 2>&1 &
AGENT_PID=$!
echo "[+] Agent started with PID: $AGENT_PID. Log: $SCRIPT_DIR/agent.log"

echo ""
echo "[*] C2 services started successfully."
echo "[*] The C2 Control Panel GUI should open automatically."
echo "[*] To stop the services, you can use: kill $SERVER_PID $AGENT_PID"
