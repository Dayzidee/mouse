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
    def __init__(self, send_queue: Queue, receive_queue: Queue, server_event_queue: Queue):
        self.host = HOST
        self.port = PORT
        self.send_queue = send_queue
        self.receive_queue = receive_queue
        self.server_event_queue = server_event_queue
        self.clients = {}
        self.shutdown_event = threading.Event()

    def _receive_file(self, client_socket, agent_id, token):
        try:
            file_size_data = client_socket.recv(8)
            if not file_size_data: raise ConnectionError("Disconnected while reading file size")
            file_size = struct.unpack('>Q', file_size_data)[0]
            
            self.receive_queue.put({'type': 'STS', 'agent_id': agent_id, 'token': token, 'payload': f"Receiving file ({file_size} bytes)..."})

            file_data = b''
            bytes_to_read = file_size
            while len(file_data) < file_size:
                chunk = client_socket.recv(min(4096, bytes_to_read))
                if not chunk: raise ConnectionError("Client disconnected during file transfer")
                file_data += chunk
                bytes_to_read -= len(chunk)
            
            save_path = f"download_{token}.png"
            with open(save_path, 'wb') as f: f.write(file_data)
            
            self.receive_queue.put({'type': 'RSP', 'agent_id': agent_id, 'token': token, 'payload': f"File saved successfully as '{save_path}'."})
        except (struct.error, ConnectionError) as e:
            print(f"[Network] Error receiving file from {agent_id}: {e}")
            raise ConnectionError("File receive failed") # Propagate to disconnect handler

    def _client_handler_thread(self, client_socket, client_address):
        agent_id = None
        try:
            # First message must be identification
            id_message = Protocol.unpack_message(client_socket)
            if id_message and id_message.get('type') == 'ID_AGENT':
                agent_id = id_message.get('agent_id')
                if not agent_id:
                    print("[!] Agent failed to provide an ID.")
                    return

                print(f"[Network] Agent {agent_id} identified from {client_address}")
                self.clients[agent_id] = client_socket
                self.server_event_queue.put({'type': 'AGENT_CONNECTED', 'agent_id': agent_id})
            else:
                print(f"[!] No valid identification from {client_address}. Closing connection.")
                return

            # Main message loop
            while not self.shutdown_event.is_set():
                header_bytes = client_socket.recv(4)
                if not header_bytes: break

                if header_bytes == b'[FIL':
                    client_socket.recv(1) # Consume the final ']'
                    token_len_data = client_socket.recv(4)
                    if not token_len_data: break
                    token_len = struct.unpack('>I', token_len_data)[0]
                    token = client_socket.recv(token_len).decode('utf-8')
                    self._receive_file(client_socket, agent_id, token)
                else:
                    # It's a standard JSON message that Protocol can handle
                    message = Protocol.unpack_message_from_header(header_bytes, client_socket)
                    if message is None:
                        break # Client disconnected
                    
                    message['agent_id'] = agent_id # Tag message with agent ID
                    self.receive_queue.put(message)

        except (ConnectionError, OSError, struct.error, json.JSONDecodeError) as e:
            print(f"[!] Error with agent {agent_id if agent_id else 'unknown'}: {e}")
        
        finally:
            if agent_id and agent_id in self.clients:
                print(f"[Network] Agent {agent_id} disconnected.")
                self.server_event_queue.put({'type': 'AGENT_DISCONNECTED', 'agent_id': agent_id})
                del self.clients[agent_id]

            client_socket.close()

    def _send_messages_thread(self):
        print("[Network] Ready to send messages to agents...")
        while not self.shutdown_event.is_set():
            try:
                message_data = self.send_queue.get(timeout=1)
                agent_id = message_data.get('agent_id')
                client_socket = self.clients.get(agent_id)

                if client_socket:
                    packed_message = Protocol.pack_message(message_data)
                    if packed_message:
                        client_socket.sendall(packed_message)
                else:
                    print(f"[Network] Agent {agent_id} not found for sending message.")

                self.send_queue.task_done()
            except queue.Empty: continue
            except (ConnectionError, ssl.SSLError): break

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
        server_socket.listen(5)
        print(f"[*] Server listening securely on {self.host}:{self.port}")

        threading.Thread(target=self._send_messages_thread, daemon=True).start()

        while not self.shutdown_event.is_set():
            try:
                conn, addr = server_socket.accept()
                print(f"[+] Incoming connection from: {addr[0]}:{addr[1]}")
                client_socket = context.wrap_socket(conn, server_side=True)

                thread = threading.Thread(target=self._client_handler_thread, args=(client_socket, addr), daemon=True)
                thread.start()

            except (ssl.SSLError, OSError) as e:
                if not self.shutdown_event.is_set(): print(f"[!] Server socket error: {e}")
                break
        
        server_socket.close()
        print("[Network] Server has shut down.")

    def stop(self):
        self.shutdown_event.set()
        for agent_id, client_socket in self.clients.items():
            try:
                client_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client_socket.close()
        self.clients.clear()

        try:
            with socket.create_connection((self.host if self.host != '0.0.0.0' else '127.0.0.1', self.port), timeout=1) as s:
                pass
        except (ConnectionRefusedError, socket.timeout):
            pass