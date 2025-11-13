import threading
import time
import uuid
import queue
import shlex

from server.network_handler import ServerNetworkHandler
from server.config import COMMAND_TIMEOUT

class AppController:
    def __init__(self, gui_queue: queue.Queue):
        self.gui_queue = gui_queue
        self.send_queue = queue.Queue()
        self.receive_queue = queue.Queue()
        self.server_event_queue = queue.Queue()
        
        self.network_handler = ServerNetworkHandler(self.send_queue, self.receive_queue, self.server_event_queue)
        self.in_flight_commands = {} # agent_id -> {token: details}
        self.shutdown_event = threading.Event()
        self.agents = {} # agent_id -> status

    def _generate_token(self):
        return f"cmd_{uuid.uuid4().hex[:8]}"

    def _command_timeout_handler(self, agent_id, token):
        if agent_id in self.in_flight_commands and token in self.in_flight_commands[agent_id]:
            command_details = self.in_flight_commands[agent_id].pop(token)
            command_name = command_details['command']
            self.log_to_gui(f"[!] ERROR: Command '{command_name}' for agent {agent_id} (token: {token}) timed out.", 'ERR')
            self.gui_queue.put({'type': 'COMMAND_COMPLETED', 'agent_id': agent_id})

    def _process_server_events(self):
        while not self.shutdown_event.is_set():
            try:
                event = self.server_event_queue.get(timeout=1)
                event_type = event.get('type')
                agent_id = event.get('agent_id')

                if event_type == 'AGENT_CONNECTED':
                    self.agents[agent_id] = 'Connected'
                    self.log_to_gui(f"[*] Agent {agent_id} connected.", 'STS')
                    self.gui_queue.put({'type': 'AGENT_STATUS_UPDATE', 'agent_id': agent_id, 'status': 'Connected'})
                elif event_type == 'AGENT_DISCONNECTED':
                    if agent_id in self.agents:
                        del self.agents[agent_id]
                    self.log_to_gui(f"[-] Agent {agent_id} disconnected.", 'ERR')
                    self.gui_queue.put({'type': 'AGENT_STATUS_UPDATE', 'agent_id': agent_id, 'status': 'Disconnected'})
                    if agent_id in self.in_flight_commands:
                        for token, details in self.in_flight_commands[agent_id].items():
                            details['timer'].cancel()
                            self.log_to_gui(f"[!] CRITICAL: Agent {agent_id} disconnected during command '{details['command']}'.", 'ERR')
                        del self.in_flight_commands[agent_id]
                        self.gui_queue.put({'type': 'COMMAND_COMPLETED', 'agent_id': agent_id})
            except queue.Empty:
                continue

    def process_incoming_messages(self):
        while not self.shutdown_event.is_set():
            try:
                message = self.receive_queue.get(timeout=1)
                msg_type = message.get('type')
                token = message.get('token')
                payload = message.get('payload', 'No payload received.')
                agent_id = message.get('agent_id') # Assuming agent sends its ID

                if agent_id in self.in_flight_commands and token in self.in_flight_commands[agent_id]:
                    command_details = self.in_flight_commands[agent_id][token]
                    
                    if msg_type in ('RSP', 'ERR'):
                        command_details['timer'].cancel()
                        del self.in_flight_commands[agent_id][token]
                        self.gui_queue.put({'type': 'COMMAND_COMPLETED', 'agent_id': agent_id})
                    
                    log_tag = msg_type if msg_type in ('STS', 'ERR') else 'INFO'
                    self.log_to_gui(f"[<] From {agent_id} ({token}):\n{payload}", log_tag)
                else:
                    self.log_to_gui(f"[!] Received message from {agent_id} with unknown token: {token}", 'ERR')
                
                self.receive_queue.task_done()
            except queue.Empty:
                continue

    def send_command_to_agent(self, agent_id, command_string):
        if agent_id not in self.agents:
            self.log_to_gui(f"[!] Cannot send command: Agent {agent_id} is not connected.", 'ERR')
            return

        # This logic may need to be adjusted based on whether you allow multiple commands per agent
        if agent_id in self.in_flight_commands and self.in_flight_commands[agent_id]:
            self.log_to_gui(f"[!] Cannot send command to {agent_id}: Another command is in progress.", 'ERR')
            return

        try:
            parts = shlex.split(command_string)
            command = parts[0]
            args = parts[1:]
        except IndexError:
            return # Empty command

        token = self._generate_token()
        message = {"token": token, "command": command, "args": args, "agent_id": agent_id}
        
        timer = threading.Timer(COMMAND_TIMEOUT, self._command_timeout_handler, [agent_id, token])
        if agent_id not in self.in_flight_commands:
            self.in_flight_commands[agent_id] = {}
        self.in_flight_commands[agent_id][token] = {"command": command, "timer": timer}
        
        self.log_to_gui(f"[>] Sending '{command}' to {agent_id} (token: {token})", 'CMD')
        self.send_queue.put(message)
        timer.start()
        self.gui_queue.put({'type': 'COMMAND_SENT', 'agent_id': agent_id})

    def log_to_gui(self, message, tag='INFO'):
        self.gui_queue.put({'type': 'LOG', 'payload': message, 'tag': tag})

    def start(self):
        self.log_to_gui("[*] Controller starting...")

        network_thread = threading.Thread(target=self.network_handler.start, daemon=True)
        network_thread.start()

        server_event_thread = threading.Thread(target=self._process_server_events, daemon=True)
        server_event_thread.start()

        self.process_incoming_messages()

    def stop(self):
        self.shutdown_event.set()
        self.network_handler.stop()
        self.log_to_gui("[*] Controller shutting down.")