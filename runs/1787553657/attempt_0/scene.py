from manim import *

class GeneratedScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE, radius=0.5)
        self.play(MoveToTarget(circle, target_position=RIGHT*10))