from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Create a full-screen Rectangle as the background
        background = Rectangle(width=config.frame_width, height=config.frame_height, color=[BLUE_E, PURPLE_E, BLACK])
        self.add(background)

        # Define a custom hex string for neon blue
        NEON_BLUE = "#00FFFF"

        # Create a central white Circle nucleus
        nucleus = Circle(color=WHITE)
        self.add(nucleus)

        # Define orbital pathways using Ellipse and Circle
        orbit1 = Circle(color=RED, radius=2)
        orbit2 = Circle(color=GREEN, radius=1.5)
        orbit3 = Circle(color=BLUE, radius=1)

        # Rotate the orbits around the nucleus
        orbit1.rotate(PI / 4)
        orbit2.rotate(PI / 2)
        orbit3.rotate(3 * PI / 4)

        # Create Dot objects to represent electrons
        electron1 = Dot(color=NEON_BLUE)
        electron2 = Dot(color=NEON_BLUE)
        electron3 = Dot(color=NEON_BLUE)

        # Position the electrons on the orbits
        electron1.move_to(orbit1)
        electron2.move_to(orbit2)
        electron3.move_to(orbit3)

        # Animate the electrons flowing on the pathways
        animations = [MoveAlongPath(electron1, orbit1), MoveAlongPath(electron2, orbit2), MoveAlongPath(electron3, orbit3)]
        self.play(*animations)

        # Simulate the flowing background color shift
        background_gradient = [PURPLE_E, BLUE_E, BLACK]
        self.play(Transform(background, Rectangle(width=config.frame_width, height=config.frame_height, color=background_gradient)), run_time=5)