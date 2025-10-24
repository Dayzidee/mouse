import subprocess
import os
import pyautogui
import tempfile

class CommandService:
    """Handles the execution of general system commands like cmd and screenshot."""

    def execute_shell_command(self, command: str) -> str:
        """Runs a command in the system's shell and captures the output."""
        if not command:
            return "[Error] No command provided for execution."
        try:
            # shell=True allows using shell features, but should be used with trusted input.
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                errors='ignore'
            )
            output = result.stdout + result.stderr
            return output if output else "[No output]"
        except Exception as e:
            return f"[Error] Failed to execute shell command: {e}"

    def take_screenshot(self) -> tuple[str | None, str | None]:
        """
        Takes a screenshot and saves it to a temporary file.
        Returns a tuple: (filepath, error_message). On success, error_message is None.
        """
        try:
            # Create a temporary file in a cross-platform way
            fd, filepath = tempfile.mkstemp(suffix=".png")
            os.close(fd) # Close the file descriptor
            
            pyautogui.screenshot(filepath)
            return filepath, None
        except Exception as e:
            return None, f"[Error] Failed to take screenshot: {e}"