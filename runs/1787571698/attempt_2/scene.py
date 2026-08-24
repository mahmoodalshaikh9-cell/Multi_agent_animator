from manim import *

class GeneratedScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE)
        self.play(Create(circle))
        self.play(circle.animate.shift(RIGHT * 5))
        title = Text("Hello World", color=YELLOW).to_edge(UP)
        self.play(Write(title))
        self.wait(3)