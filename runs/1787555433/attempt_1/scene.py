from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Create a number line
        number_line = NumberLine(x_range=[-4, 4, 1])
        number_line.add_numbers([-4, -3, -2, -1, 0, 1, 2, 3, 4])
        number_line.set_color(BLUE)
        self.play(Create(number_line))

        # Create a green dot
        dot = Dot(color=GREEN)
        dot.move_to(number_line.n2p(-4))
        self.play(Create(dot))

        # Create a yellow sine wave
        sine_wave = ParametricFunction(
            lambda t: [t, np.sin(t), 0],
            t_min=-4,
            t_max=4,
            color=YELLOW
        )
        self.play(Create(sine_wave))

        # Show the equation y = sin(x) at the bottom
        equation = Text("y = sin(x)", color=BLACK).to_edge(DOWN)
        self.play(Write(equation))

        # Animate the dot moving along the number line
        self.play(dot.animate.shift(RIGHT * 8), run_time=4)

        # Fade out the sine wave and equation
        self.play(FadeOut(sine_wave), FadeOut(equation))