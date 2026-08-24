from manim import *

class GeneratedScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE)
        square = Square(color=RED)
        
        self.play(ReplacementTransform(circle, square), run_time=2)