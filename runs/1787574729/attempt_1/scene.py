from manim import *

class ElectronOrbit(Scene):
    def construct(self):
        # Create a 3D scene
        self.camera.frame.add(Dot(color=RED).shift(ORIGIN))

        # Create the nucleus
        nucleus = Circle(radius=0.5, color=RED)
        self.add(nucleus)

        # Create the electrons
        electrons = VGroup(*[Dot(color=Color(hue=h, saturation=0.5, value=0.5)).shift(RIGHT * h * 10) for h in np.linspace(0, 1, 100)])
        self.add(electrons)

        # Animate the camera orbiting the nucleus
        self.play(self.camera.animate.set_position(ORIGIN), run_time=10)

        # Animate the electrons flowing along the orbit
        for electron in electrons:
            self.play(electron.animate.shift(RIGHT * 5), run_time=1)

        self.wait()