import socket
import ssl
import time
import threading
import uuid
from queue import Queue, Empty

# Import our custom components
from shared.protocol import Protocol
from agent.config import SERVER_HOST, SERVER_PORT, RECONNECT_DELAY

class AgentNetworkHandler:
    def __init__(self, send_queue: Queue, receive_queue: Queue):
        self.host = SERVER_HOST
        self.port = SERVER_PORT
        self.reconnect_delay = RECONNECT_DELAY
        self.send_queue = send_queue
        self.receive_queue = receive_queue
        self.sock = None
        self.is_connected = False
        self.shutdown_event = threading.Event()
        self.agent_id = f"agent_{uuid.uuid4().hex[:8]}"

    def _connect(self):
        """Handles the persistent connection logic."""
        while not self.shutdown_event.is_set():
            try:
                print(f"[*] Attempting to connect to {self.host}:{self.port}...")
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                
                raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock = context.wrap_socket(raw_sock, server_hostname=self.host)
                self.sock.connect((self.host, self.port))
                
                print("[+] Successfully connected to the server.")
                self.is_connected = True

                # Identify with the server
                id_message = {"type": "ID_AGENT", "agent_id": self.agent_id}
                self.sock.sendall(Protocol.pack_message(id_message))
                print(f"[*] Identified to server as {self.agent_id}")
                return
            except (ConnectionRefusedError, socket.gaierror, ssl.SSLError, OSError) as e:
                print(f"[!] Connection failed: {e}. Retrying in {self.reconnect_delay} seconds.")
                time.sleep(self.reconnect_delay)

    def _listen_for_messages(self):
        """Listens for incoming messages and puts them on the receive queue."""
        while self.is_connected and not self.shutdown_event.is_set():
            message = Protocol.unpack_message(self.sock)
            if message is None:
                print("[-] Server disconnected.")
                self.is_connected = False
                break
            self.receive_queue.put(message)

    def _send_messages(self):
        """Sends messages from the send queue to the server."""
        while self.is_connected and not self.shutdown_event.is_set():
            try:
                message_data = self.send_queue.get(timeout=1) # Timeout to allow checking shutdown event
                packed_message = Protocol.pack_message(message_data)
                if packed_message and self.sock:
                    self.sock.sendall(packed_message)
                self.send_queue.task_done()
            except Empty:
                continue
            except (ConnectionError, ssl.SSLError):
                print("[-] Server disconnected during send.")
                self.is_connected = False
                break
    
    def start(self):
        """The main loop for the network handler."""
        while not self.shutdown_event.is_set():
            self._connect()
            if self.is_connected:
                # Start listener and sender threads
                listener_thread = threading.Thread(target=self._listen_for_messages, daemon=True)
                sender_thread = threading.Thread(target=self._send_messages, daemon=True)
                listener_thread.start()
                sender_thread.start()

                # Wait for the listener to finish (which happens on disconnect)
                listener_thread.join()
                sender_thread.join()
            
            if self.sock:
                self.sock.close()

    def stop(self):
        """Stops the network handler gracefully."""
        self.shutdown_event.set()
        if self.sock:
            self.sock.close()
