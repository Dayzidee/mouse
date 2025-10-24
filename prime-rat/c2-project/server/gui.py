import tkinter as tk
from tkinter import scrolledtext
from queue import Queue

class ControlPanelGUI:
    def __init__(self, root, controller_command_queue: Queue, gui_queue: Queue):
        self.root = root
        self.controller_command_queue = controller_command_queue
        self.gui_queue = gui_queue
        
        self.root.title("C2 Control Panel - Agent: Disconnected")
        
        self.log_text = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=100, height=35, bg="black", fg="lime green", font=("Consolas", 10))
        self.log_text.pack(pady=5, padx=5, expand=True, fill=tk.BOTH)
        self._configure_tags()

        self.command_entry = tk.Entry(root, width=80, bg="#1c1c1c", fg="white", insertbackground="white", font=("Consolas", 10))
        self.command_entry.pack(pady=5, padx=5, fill=tk.X)
        self.command_entry.bind("<Return>", self._send_command_event)
        
        self.root.after(100, self._process_gui_queue)

    def _configure_tags(self):
        self.log_text.tag_config('STS', foreground='cyan')
        self.log_text.tag_config('ERR', foreground='red')
        self.log_text.tag_config('CMD', foreground='yellow')
        self.log_text.tag_config('INFO', foreground='white')

    def _send_command_event(self, event=None):
        command = self.command_entry.get().strip()
        if not command: return
        self.command_entry.delete(0, tk.END)
        self.controller_command_queue.put({'command': command})

    def _process_gui_queue(self):
        try:
            while not self.gui_queue.empty():
                message = self.gui_queue.get_nowait()
                msg_type = message.get('type')

                if msg_type == 'LOG':
                    self.log_text.insert(tk.END, message['payload'] + "\n", message['tag'])
                elif msg_type == 'COMMAND_SENT':
                    self.command_entry.config(state='disabled', bg='#555555')
                elif msg_type == 'COMMAND_COMPLETED':
                    self.command_entry.config(state='normal', bg='#1c1c1c')
                elif msg_type == 'AGENT_STATUS_UPDATE':
                    self.root.title(f"C2 Control Panel - Agent: {message['status']}")
                
                self.gui_queue.task_done()
        finally:
            self.log_text.see(tk.END)
            self.root.after(100, self._process_gui_queue)