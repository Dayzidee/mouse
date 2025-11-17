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
        
        self.network_handler = ServerNetworkHandler(self.send_queue, self.receive_queue)
        self.in_flight_commands = {} # Tracks commands waiting for a response
        self.shutdown_event = threading.Event()
        self.agent_connected = False

    def _generate_token(self):
        return f"cmd_{uuid.uuid4().hex[:8]}"

    def _command_timeout_handler(self, token):
        if token in self.in_flight_commands:
            command_details = self.in_flight_commands.pop(token)
            command_name = command_details['command']
            self.log_to_gui(f"[!] ERROR: Command '{command_name}' (token: {token}) timed out.", 'ERR')
            self.gui_queue.put({'type': 'COMMAND_COMPLETED'})

    def process_messages(self):
        while not self.shutdown_event.is_set():
            try:
                message = self.receive_queue.get(timeout=1)
                msg_type = message.get('type')

                if msg_type == 'SYSTEM':
                    payload = message.get('payload')
                    if payload == 'AGENT_CONNECTED':
                        self.agent_connected = True
                        self.log_to_gui("[*] Agent connection established.", 'STS')
                        self.gui_queue.put({'type': 'AGENT_STATUS_UPDATE', 'status': 'Connected'})
                    elif payload == 'AGENT_DISCONNECTED':
                        self.agent_connected = False
                        self.log_to_gui("[-] Agent disconnected.", 'ERR')
                        self.gui_queue.put({'type': 'AGENT_STATUS_UPDATE', 'status': 'Disconnected'})
                        for token in list(self.in_flight_commands.keys()):
                            details = self.in_flight_commands.pop(token)
                            self.log_to_gui(f"[!] CRITICAL: Agent disconnected during command '{details['command']}'.", 'ERR')
                        self.gui_queue.put({'type': 'COMMAND_COMPLETED'})
                    continue

                token = message.get('token')
                payload = message.get('payload', 'No payload received.')

                if token and token in self.in_flight_commands:
                    command_details = self.in_flight_commands[token]
                    
                    if msg_type in ('RSP', 'ERR'):
                        command_details['timer'].cancel()
                        self.in_flight_commands.pop(token)
                        self.gui_queue.put({'type': 'COMMAND_COMPLETED'})
                    
                    log_tag = msg_type if msg_type in ('STS', 'ERR') else 'INFO'
                    self.log_to_gui(f"[<] {msg_type} (token: {token}):\n{payload}", log_tag)
                else:
                    self.log_to_gui(f"[!] Received message with unknown or stale token: {token}", 'ERR')
                
                self.receive_queue.task_done()
            except queue.Empty:
                continue

    def send_command_to_agent(self, command_string):
        if not self.agent_connected:
            self.log_to_gui("[!] Cannot send command: Agent is not connected.", 'ERR')
            return
        if self.in_flight_commands:
            self.log_to_gui("[!] Cannot send command: Another command is in progress.", 'ERR')
            return

        try:
            parts = shlex.split(command_string)
            command = parts[0]
            args = parts[1:]
        except IndexError:
            return # Empty command

        token = self._generate_token()
        message = {"token": token, "command": command, "args": args}
        
        timer = threading.Timer(COMMAND_TIMEOUT, self._command_timeout_handler, [token])
        self.in_flight_commands[token] = {"command": command, "timer": timer}
        
        self.log_to_gui(f"[>] Sending '{command}' with args {args} (token: {token})", 'CMD')
        self.send_queue.put(message)
        timer.start()
        self.gui_queue.put({'type': 'COMMAND_SENT'})

    def log_to_gui(self, message, tag='INFO'):
        self.gui_queue.put({'type': 'LOG', 'payload': message, 'tag': tag})

    def start(self):
        self.log_to_gui("[*] Controller starting...")
        network_thread = threading.Thread(target=self.network_handler.start, daemon=True)
        network_thread.start()
        self.process_messages()

    def stop(self):
        self.shutdown_event.set()
        self.network_handler.stop()
        self.log_to_gui("[*] Controller shutting down.")