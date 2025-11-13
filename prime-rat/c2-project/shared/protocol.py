import json
import struct

class Protocol:
    """
    Handles packing and unpacking of messages for the C2 protocol.
    Messages are sent as: 4-byte header (message length) + JSON payload.
    """

    @staticmethod
    def pack_message(data: dict) -> bytes:
        """Converts a Python dictionary to a JSON byte string with a length header."""
        try:
            json_payload = json.dumps(data).encode('utf-8')
            header = struct.pack('>I', len(json_payload))
            return header + json_payload
        except (TypeError, OverflowError) as e:
            print(f"[Protocol Error] Failed to pack message: {e}")
            return b''

    @staticmethod
    def unpack_message(sock) -> dict | None:
        """Reads from a socket and unpacks one complete message."""
        try:
            # Read the 4-byte header to get the payload length
            header_bytes = sock.recv(4)
            if not header_bytes:
                return None # Connection closed
            
            return Protocol.unpack_message_from_header(header_bytes, sock)

        except (struct.error, json.JSONDecodeError, ConnectionError):
            return None

    @staticmethod
    def unpack_message_from_header(header_bytes: bytes, sock) -> dict | None:
        """Unpacks a message given that the header has already been read."""
        try:
            payload_len = struct.unpack('>I', header_bytes)[0]
            
            payload_bytes = b''
            bytes_to_read = payload_len
            while len(payload_bytes) < payload_len:
                packet = sock.recv(bytes_to_read)
                if not packet:
                    return None # Connection lost
                payload_bytes += packet
                bytes_to_read -= len(packet)

            return json.loads(payload_bytes.decode('utf-8'))
        
        except (struct.error, json.JSONDecodeError, ConnectionError):
            return None