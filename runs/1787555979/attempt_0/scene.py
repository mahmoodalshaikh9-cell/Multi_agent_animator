from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Create a number line
        number_line = NumberLine(x_range=[-10, 10, 1])
        self.play(Create(number_line))

        # Create a circle at the origin
        circle = Circle(color=BLUE)
        circle.move_to(number_line.n2p(0))
        self.play(Create(circle))

        # Create a dot at the point (3, 4)
        dot = Dot(color=RED)
        dot.move_to(number_line.n2p(3))
        self.play(Create(dot))

        # Create an arrow from the origin to the point (3, 4)
        arrow = Arrow(start=number_line.n2p(0), end=number_line.n2p(3))
        self.play(Create(arrow))

        # Create a line from the origin to the point (3, 4)
        line = Line(start=number_line.n2p(0), end=number_line.n2p(3))
        self.play(Create(line))

        # Create a text label for the point (3, 4)
        label = Text("(3, 4)", color=GREEN).next_to(dot, RIGHT)
        self.play(Create(label))

        # Create a text label for the number 3
        number_label = Text("3", color=GREEN).next_to(dot, UP)
        self.play(Create(number_label))

        # Create a text label for the number 4
        number_label = Text("4", color=GREEN).next_to(dot, DOWN)
        self.play(Create(number_label))

        self.wait()