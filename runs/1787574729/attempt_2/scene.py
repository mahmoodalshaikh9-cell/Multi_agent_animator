from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Create a 3D scene
        nucleus = Circle(radius=0.5, color=RED)
        self.add(nucleus)

        # Create the electrons
        electrons = VGroup(*[Dot(color=Color(hue=h, saturation=0.5, value=0.5)).shift(RIGHT * h * 5) for h in np.linspace(0, 1, 100)])
        self.add(electrons)

        # Animate the camera orbiting the nucleus
        self.play(self.camera.move_to(nucleus), run_time=10)

        # Animate the electrons flowing along the orbit
        for electron in electrons:
            self.play(electron.animate.shift(RIGHT * 5), run_time=1)

        self.wait()