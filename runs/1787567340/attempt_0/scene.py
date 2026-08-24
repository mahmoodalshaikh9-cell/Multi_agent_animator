from manim import *

class GeneratedScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE)
        self.play(Create(circle))
        self.play(circle.animate.shift(RIGHT * 10))
        self.wait()