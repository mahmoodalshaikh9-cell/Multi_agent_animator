from manim import *

class GeneratedScene(Scene):
    def construct(self):
        square = Square(color=RED, side_length=2)
        circle = Circle(color=BLUE, radius=2)

        self.play(Create(square), Create(circle))
        self.play(square.animate.scale(2), circle.animate.scale(0.5))
        self.play(square.animate.shift(LEFT * 3), circle.animate.shift(RIGHT * 3))
        self.play(square.animate.move_to(ORIGIN), circle.animate.move_to(ORIGIN))
        self.play(Write(Text("Collision Course", color=YELLOW), at=UP))