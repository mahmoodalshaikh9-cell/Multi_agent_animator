from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Create a time line
        time_line = NumberLine(x_range=[-5, 5, 1], length=10)
        self.add(time_line)

        # Create a space line
        space_line = NumberLine(x_range=[-5, 5, 1], length=10)
        self.add(space_line)

        # Create a line representing the fabric of time and space
        fabric_line = Line([-5, -5, 0], [5, 5, 0])
        self.add(fabric_line)

        # Rotate the fabric line
        rotated_fabric_line = fabric_line.copy().rotate(PI/4)

        # Animate the rotation
        self.play(Create(fabric_line), FadeOut(time_line, space_line))
        self.play(FadeIn(rotated_fabric_line), Rotate(fabric_line, PI/4, about_point=ORIGIN))