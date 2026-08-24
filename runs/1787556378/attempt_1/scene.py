from manim import *

class GeneratedScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE)
        self.play(Create(circle))
        self.play(circle.animate.shift(RIGHT * 5))

        title = Text("Hello World", color=YELLOW).to_edge(UP)
        self.play(Write(title))
        self.wait()

        # Set up input prompt
        prompt = Text("PS> ", color=YELLOW)
        self.play(Write(prompt))

        # Capture user input and execute command
        def command_input(mobject):
            command = prompt.get_tex()[1:]  # Remove 'PS> '
            self.play(FadeOut(prompt))
            result = subprocess.run(command, capture_output=True, text=True, shell=True)
            print(result.stdout)
            if result.returncode != 0:
                error_text = Text(f"Error: {result.stderr}", color=RED)
                self.play(Write(error_text))
                self.wait()
            else:
                success_text = Text(f"Success: {result.stdout}", color=GREEN)
                self.play(Write(success_text))
                self.wait()
            self.play(FadeIn(prompt))

        self.add(prompt)
        prompt.add_updater(command_input)

        # Add exit command
        exit_text = Text("exit", color=RED)
        exit_text.next_to(prompt, DOWN)
        self.play(Write(exit_text))
        exit_text.add_updater(lambda m: m.move_to(prompt.get_tex().get_center()))

        # Handle exit command
        def handle_exit(mobject):
            self.play(FadeOut(prompt), FadeOut(exit_text))
            self.wait(2)
            self.play(Write(title))
            self.wait()
            self.remove(prompt, exit_text)

        exit_text.add_updater(handle_exit)