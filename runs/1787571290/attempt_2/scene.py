from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Create a background with a flowing gradient color
        gradient = VGroup(
            Circle(color=BLUE, radius=10).shift(LEFT * 5),
            Circle(color=GREEN, radius=10).shift(RIGHT * 5)
        )
        self.play(Create(gradient))

        # Create a group of blue balls representing electrons
        electrons = VGroup(*[Dot(color=BLUE) for _ in range(10)])
        electrons.arrange(DOWN, buff=0.1)
        electrons.move_to(UP * 3)

        # Animate the electrons flowing from left to right
        self.play(FadeIn(electrons))
        self.play(electrons.animate.shift(RIGHT * 5), run_time=2)

        # Add text to the scene
        title = Text("Electrons Flow", color=YELLOW).to_edge(UP)
        self.play(Write(title))

        self.wait()