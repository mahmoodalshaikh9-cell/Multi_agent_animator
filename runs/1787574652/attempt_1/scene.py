from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Create a 3D scene
        scene = ThreeDScene()
        scene.set_camera_orientation(phi=75 * DEGREES, theta=30 * DEGREES)
        scene.set_background_color(BLACK)

        # Create a central nucleus
        nucleus = Dot(color=RED, radius=0.5)
        self.add(nucleus)

        # Create a fluid background gradient
        gradient = self.get_gradient_background()
        self.add(gradient)

        # Create electrons as glowing spheres
        electrons = []
        for i in range(10):
            electron = Dot(color=NEON_BLUE, radius=0.1)
            electron.shift(RIGHT * 5)
            electrons.append(electron)

        # Animate the electrons orbiting the nucleus
        for electron in electrons:
            self.play(Create(electron))
            self.play(electron.animate.shift(RIGHT * 5))
            self.wait(0.1)

        # Add dynamic lighting
        self.camera.set_lights()

        # Set the resolution and frame rate
        self.camera.resolution = (8192, 4320)
        self.camera.frame_rate = 60

        # Animate the scene
        self.wait(10)