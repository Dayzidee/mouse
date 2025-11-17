import tkinter as tk
from tkinter import scrolledtext, Listbox, Frame
from queue import Queue

class ControlPanelGUI:
    def __init__(self, root, controller_command_queue: Queue, gui_queue: Queue):
        self.root = root
        self.controller_command_queue = controller_command_queue
        self.gui_queue = gui_queue
        self.agents = {}  # agent_id -> status

        self.root.title("C2 Control Panel")
        
        # Main frame
        main_frame = Frame(root)
        main_frame.pack(pady=5, padx=5, expand=True, fill=tk.BOTH)

        # Agent list
        self.agent_listbox = Listbox(main_frame, width=40, bg="#1c1c1c", fg="white", font=("Consolas", 10))
        self.agent_listbox.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))

        # Log text area
        self.log_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=100, height=35, bg="black", fg="lime green", font=("Consolas", 10))
        self.log_text.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        self._configure_tags()

        # Command entry
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
        if not command:
            return

        selected_indices = self.agent_listbox.curselection()
        if not selected_indices:
            self.log_text.insert(tk.END, "[!] No agent selected. Cannot send command.\n", 'ERR')
            return

        selected_agent_id = self.agent_listbox.get(selected_indices[0])
        self.command_entry.delete(0, tk.END)

        self.controller_command_queue.put({'agent_id': selected_agent_id, 'command': command})

    def _process_gui_queue(self):
        try:
            while not self.gui_queue.empty():
                message = self.gui_queue.get_nowait()
                msg_type = message.get('type')
                agent_id = message.get('agent_id')

                if msg_type == 'LOG':
                    self.log_text.insert(tk.END, message['payload'] + "\n", message['tag'])

                elif msg_type == 'AGENT_STATUS_UPDATE':
                    status = message.get('status')
                    if status == 'Connected':
                        if agent_id not in self.agents:
                            self.agents[agent_id] = status
                            self.agent_listbox.insert(tk.END, agent_id)
                    elif status == 'Disconnected':
                        if agent_id in self.agents:
                            del self.agents[agent_id]
                            for i, item in enumerate(self.agent_listbox.get(0, tk.END)):
                                if item == agent_id:
                                    self.agent_listbox.delete(i)
                                    break

                elif msg_type == 'COMMAND_SENT':
                    # Maybe disable entry only for the selected agent in future
                    self.command_entry.config(state='disabled', bg='#555555')

                elif msg_type == 'COMMAND_COMPLETED':
                    self.command_entry.config(state='normal', bg='#1c1c1c')
                
                self.gui_queue.task_done()
        finally:
            self.log_text.see(tk.END)
            self.root.after(100, self._process_gui_queue)
