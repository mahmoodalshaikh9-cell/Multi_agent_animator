from manim import *

class GeneratedScene(MovingCameraScene):
    def construct(self):
        # Set camera properties
        self.camera.lights.color = BLUE
        self.camera.lights.intensity = 2
        self.camera.shutter_speed = 0.001
        self.camera.film_resolution = (8192, 8192)
        self.camera.frame_rate = 60

        # Create the atomic nucleus
        nucleus = Sphere(radius=0.5, color=WHITE)
        self.add(nucleus)

        # Create the electrons
        electrons = []
        for i in range(10):
            electron = Sphere(radius=0.1, color="#00FFFF")
            electron.shift(RIGHT * (i - 4) * 2)
            electrons.append(electron)
            self.add(electron)

        # Create the background gradient
        gradient = ParametricSurface(
            lambda u, v: [u, v, 0],
            u_min=-1, u_max=1, v_min=-1, v_max=1,
            checkerboard_colors=[BLUE, GREEN],
            resolution=(50, 50)
        )
        gradient.set_opacity(0.5)
        self.add(gradient)

        # Animate the camera orbiting the nucleus
        self.play(self.camera.frame.animate.to_edge(UP))

        # Animate the electrons flowing and racing along the orbital pathways
        for electron in electrons:
            electron.animate.shift(RIGHT * 2)
            self.wait(0.1)

        # Animate the scene
        self.wait(10)