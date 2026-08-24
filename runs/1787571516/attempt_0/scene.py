from manim import *

class AtomVisualization(Scene):
    def construct(self):
        # Define the background
        background = BackgroundColor(color=Color(0x000000))
        self.add(background)

        # Create the central nucleus
        nucleus = Circle(radius=0.5, color=WHITE)
        self.add(nucleus)

        # Create the electrons
        electrons = []
        for i in range(10):
            electron = Dot(radius=0.1, color=NEON_BLUE)
            electron.shift(RIGHT * 3)
            electrons.append(electron)
            self.add(electron)

        # Create the orbital pathways
        orbitals = []
        for i in range(10):
            orbital = Circle(radius=1, color=NEON_BLUE)
            orbital.shift(RIGHT * 3)
            orbitals.append(orbital)
            self.add(orbital)

        # Animate the electrons orbiting the nucleus
        for i in range(10):
            self.play(
                electrons[i].animate.shift(LEFT * 3),
                orbitals[i].animate.shift(LEFT * 3),
                run_time=1,
                rate_func=linear
            )

        # Animate the camera orbiting the nucleus
        self.play(
            nucleus.animate.shift(LEFT * 3),
            orbitals[i].animate.shift(LEFT * 3),
            run_time=10,
            rate_func=linear
        )

        # Add dynamic lighting and motion blur
        self.camera.set_lights(color=NEON_BLUE)
        self.camera.set_motion_blur(True)
        self.camera.set_shutter_speed(1/60)

        # Set the resolution and frame rate
        self.camera.resolution = (8192, 8192)
        self.camera.frame_rate = 60

        # Fade out the background
        self.play(FadeOut(background))

        # Wait for the animation to finish
        self.wait()