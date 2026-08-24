import subprocess

class PowerShellPrompt:
    def __init__(self):
        self.prompt = "PS> "

    def run_command(self, command):
        try:
            result = subprocess.run(command, capture_output=True, text=True, shell=True)
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error: {e.stderr}")

    def get_input(self):
        return input(self.prompt)

    def run(self):
        while True:
            command = self.get_input()
            if command.lower() == "exit":
                break
            self.run_command(command)

if __name__ == "__main__":
    prompt = PowerShellPrompt()
    prompt.run()