from manim import *

class GeneratedScene(Scene):
    def construct(self):
        number_line = NumberLine(x_range=[-4, 4, 1])
        number_line.add_numbers([-4, -3, -2, -1, 0, 1, 2, 3, 4])
        number_line.add_labels([-4, -3, -2, -1, 0, 1, 2, 3, 4])
        number_line.set_color(BLUE)
        self.play(Create(number_line))

        dot = Dot(color=GREEN)
        dot.move_to(number_line.number_to_point(-4))
        self.play(Create(dot))

        sine_wave = FunctionGraph(lambda x: np.sin(x), x_range=[-4, 4, 0.01], color=YELLOW)
        self.play(Create(sine_wave))

        equation_text = Text("y = sin(x)", color=RED).next_to(sine_wave, DOWN)
        self.play(Write(equation_text))

        dot_animation = AnimationGroup(dot.animate.shift(RIGHT * 8), dot.animate.shift(LEFT * 8))
        self.play(dot_animation, run_time=5)
        self.wait()