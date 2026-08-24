from manim import *

class GeneratedScene(Scene):
    def construct(self):
        square = Square(color=RED)
        circle = Circle(color=BLUE)

        self.play(Create(square), Create(circle))

        self.play(square.animate.scale(2), circle.animate.scale(0.5))

        self.play(square.animate.shift(LEFT * 3), circle.animate.shift(RIGHT * 3))

        title = Text("Collision Course", color=YELLOW).to_edge(UP)
        self.play(Write(title))

        self.wait()