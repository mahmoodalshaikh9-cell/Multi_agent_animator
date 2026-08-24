from manim import *

class GeneratedScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE).move_to(ORIGIN)
        self.play(Create(circle))
        self.wait()