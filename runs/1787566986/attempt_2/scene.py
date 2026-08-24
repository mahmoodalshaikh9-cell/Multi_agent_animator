from manim import *

class GeneratedScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE, fill_opacity=1)
        self.play(Create(circle))
        circle.shift(RIGHT * 5)
        circle.set_color(RED)  # Change color to ensure it's consistent
        title = Text("Hello World", color=YELLOW).to_edge(UP)
        self.play(Write(title))
        self.wait()