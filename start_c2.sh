#!/bin/bash

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Define paths relative to the script's location
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
SERVER_DIR="$SCRIPT_DIR/prime-rat/c2-project/server"
AGENT_DIR="$SCRIPT_DIR/prime-rat/c2-project/agent"
SERVER_MAIN="$SERVER_DIR/main_server.py"
AGENT_MAIN="$AGENT_DIR/main_agent.py"
CERT_FILE="$SERVER_DIR/server.crt"
KEY_FILE="$SERVER_DIR/server.key"
SERVER_PID_FILE="$SCRIPT_DIR/server.pid"
AGENT_PID_FILE="$SCRIPT_DIR/agent.pid"

# Function to print usage
usage() {
    echo "Usage: $0 {start|stop}"
    exit 1
}

# Function to clean up background processes and PID files
cleanup() {
    echo -e "${YELLOW}[*] Cleaning up background processes...${NC}"
    if [ -f "$SERVER_PID_FILE" ]; then
        kill $(cat "$SERVER_PID_FILE") 2>/dev/null
        rm "$SERVER_PID_FILE"
    fi
    if [ -f "$AGENT_PID_FILE" ]; then
        kill $(cat "$AGENT_PID_FILE") 2>/dev/null
        rm "$AGENT_PID_FILE"
    fi
    echo -e "${GREEN}[+] Cleanup complete.${NC}"
}

# Trap script exit to ensure cleanup
trap cleanup EXIT

# Function to start the services
start_services() {
    # 1. Check for certificates
    echo -e "${YELLOW}[*] Checking for SSL certificates...${NC}"
    if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
        echo -e "${RED}[!] ERROR: SSL certificates (server.crt, server.key) not found in $SERVER_DIR.${NC}"
        echo -e "${RED}[!] Please generate them before starting the C2 server.${NC}"
        exit 1
    fi
    echo -e "${GREEN}[+] Certificates found.${NC}"

    # 2. Launch the server in the background
    echo -e "${YELLOW}[*] Starting the C2 server in the background...${NC}"
    python3 "$SERVER_MAIN" > "$SCRIPT_DIR/server.log" 2>&1 &
    echo $! > "$SERVER_PID_FILE"
    echo -e "${GREEN}[+] Server started with PID: $(cat $SERVER_PID_FILE). Log: $SCRIPT_DIR/server.log${NC}"

    # 3. Launch the agent in the background
    echo -e "${YELLOW}[*] Starting the C2 agent in the background...${NC}"
    python3 "$AGENT_MAIN" > "$SCRIPT_DIR/agent.log" 2>&1 &
    echo $! > "$AGENT_PID_FILE"
    echo -e "${GREEN}[+] Agent started with PID: $(cat $AGENT_PID_FILE). Log: $SCRIPT_DIR/agent.log${NC}"

    echo ""
    echo -e "${GREEN}[*] C2 services started successfully.${NC}"
    echo -e "${YELLOW}[*] The C2 Control Panel GUI should open automatically.${NC}"
    echo -e "${YELLOW}[*] To stop the services, run: $0 stop${NC}"
}

# Function to stop the services
stop_services() {
    echo -e "${YELLOW}[*] Stopping C2 services...${NC}"
    cleanup
}

# Main script logic
case "$1" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    *)
        usage
        ;;
esac
