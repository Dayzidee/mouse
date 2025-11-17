import socket
import ssl
import threading
import struct
import json
import queue
from queue import Queue

from shared.protocol import Protocol
from server.config import HOST, PORT, CERTFILE, KEYFILE

class ServerNetworkHandler:
    def __init__(self, send_queue: Queue, receive_queue: Queue):
        self.host = HOST
        self.port = PORT
        self.send_queue = send_queue
        self.receive_queue = receive_queue
        self.client_socket = None
        self.shutdown_event = threading.Event()

    def _receive_file(self, token):
        try:
            if not self.client_socket:
                raise ConnectionError("No active connection")
            file_size_data = self.client_socket.recv(8)
            if not file_size_data: raise ConnectionError("Disconnected while reading file size")
            file_size = struct.unpack('>Q', file_size_data)[0]
            
            self.receive_queue.put({'type': 'STS', 'token': token, 'payload': f"Receiving file ({file_size} bytes)..."})

            file_data = b''
            bytes_to_read = file_size
            while len(file_data) < file_size:
                chunk = self.client_socket.recv(min(4096, bytes_to_read))
                if not chunk: raise ConnectionError("Client disconnected during file transfer")
                file_data += chunk
                bytes_to_read -= len(chunk)
            
            save_path = f"download_{token}.png"
            with open(save_path, 'wb') as f: f.write(file_data)
            
            self.receive_queue.put({'type': 'RSP', 'token': token, 'payload': f"File saved successfully as '{save_path}'."})
        except (struct.error, ConnectionError) as e:
            print(f"[Network] Error receiving file: {e}")
            self.receive_queue.put({'type': 'SYSTEM', 'payload': 'AGENT_DISCONNECTED'})

    def _listen_for_messages(self):
        if not self.client_socket:
            print("[Network] No active connection")
            return

        print("[Network] Listening for agent messages...")
        while not self.shutdown_event.is_set():
            try:
                # Read the first 4 bytes to determine message type or length
                header_bytes = self.client_socket.recv(4)
                if not header_bytes: break

                # Check for our special file header '[FIL'
                if header_bytes == b'[FIL':
                    self.client_socket.recv(1) # Consume the final ']'
                    token_len_data = self.client_socket.recv(4)
                    if not token_len_data: break
                    token_len = struct.unpack('>I', token_len_data)[0]
                    token = self.client_socket.recv(token_len).decode('utf-8')
                    self._receive_file(token)
                else:
                    # It's a standard JSON message
                    payload_len = struct.unpack('>I', header_bytes)[0]
                    payload_bytes = b''
                    while len(payload_bytes) < payload_len:
                        packet = self.client_socket.recv(payload_len - len(payload_bytes))
                        if not packet: raise ConnectionError("Disconnected during payload read")
                        payload_bytes += packet
                    
                    message = json.loads(payload_bytes.decode('utf-8'))
                    self.receive_queue.put(message)

            except (ConnectionError, OSError, struct.error, json.JSONDecodeError):
                break
        
        print("[Network] Agent disconnected.")
        self.receive_queue.put({'type': 'SYSTEM', 'payload': 'AGENT_DISCONNECTED'})

    def _send_messages(self):
        print("[Network] Ready to send messages to agent...")
        while not self.shutdown_event.is_set():
            try:
                message_data = self.send_queue.get(timeout=1)
                packed_message = Protocol.pack_message(message_data)
                if packed_message and self.client_socket: self.client_socket.sendall(packed_message)
                self.send_queue.task_done()
            except queue.Empty: continue
            except (ConnectionError, ssl.SSLError): break

    def _handle_client_connection(self):
        listener_thread = threading.Thread(target=self._listen_for_messages, daemon=True)
        sender_thread = threading.Thread(target=self._send_messages, daemon=True)
        listener_thread.start()
        sender_thread.start()
        listener_thread.join()
        if self.client_socket: self.client_socket.close()
        self.client_socket = None
        print("[Network] Client connection handled and closed.")

    def start(self):
        print("[Network] Initializing SSL context...")
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        try:
            context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
        except FileNotFoundError:
            print(f"[!] FATAL: Could not find '{CERTFILE}' or '{KEYFILE}'.")
            return

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(1)
        print(f"[*] Server listening securely on {self.host}:{self.port}")

        while not self.shutdown_event.is_set():
            try:
                conn, addr = server_socket.accept()
                print(f"[+] Agent connected from: {addr[0]}:{addr[1]}")
                self.client_socket = context.wrap_socket(conn, server_side=True)
                self.receive_queue.put({'type': 'SYSTEM', 'payload': 'AGENT_CONNECTED'})
                self._handle_client_connection()
            except (ssl.SSLError, OSError) as e:
                if not self.shutdown_event.is_set(): print(f"[!] Server socket error: {e}")
                break
        
        server_socket.close()
        print("[Network] Server has shut down.")

    def stop(self):
        self.shutdown_event.set()
        try:
            with socket.create_connection((self.host if self.host != '0.0.0.0' else '127.0.0.1', self.port), timeout=1) as s:
                pass
        except (ConnectionRefusedError, socket.timeout):
            pass
        if self.client_socket:
            try: self.client_socket.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            self.client_socket.close()