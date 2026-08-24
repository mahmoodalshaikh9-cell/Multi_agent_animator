from manim import *

class GeneratedScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE, radius=0.5)
        self.play(circle.animate.shift(RIGHT * 5))