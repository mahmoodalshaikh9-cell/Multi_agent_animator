from manim import *

class GeneratedScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE, radius=2)
        self.add(circle)
        self.play(circle.animate.shift(RIGHT * 5))
        self.wait()