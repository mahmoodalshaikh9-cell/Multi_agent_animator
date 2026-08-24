from manim import *

class GeneratedScene(Scene):
    def construct(self):
        num_terms = 50
        def square_wave(t):
            return 2 * (t - np.floor(t + 0.5)) - 1
        def fourier_series_approximation(t, num_terms):
            approximation = 0
            for k in range(1, num_terms + 1):
                approximation += (2 / (k * np.pi)) * np.sin(k * np.pi * t)
            return approximation

        axes = Axes(x_range=[-1, 1, 1], y_range=[-1.2, 1.2, 1])
        self.add(axes)

        square_wave_curve = axes.plot(square_wave, x_range=[-1, 1, 0.01])
        self.add(square_wave_curve)

        fourier_series_curve = axes.plot(fourier_series_approximation, x_range=[-1, 1, 0.01], color=RED)
        self.add(fourier_series_curve)

        axes.set_axis_labels(x_label="$t$", y_label="$f(t)$")
        self.play(FadeIn(axes))
        self.wait(2)