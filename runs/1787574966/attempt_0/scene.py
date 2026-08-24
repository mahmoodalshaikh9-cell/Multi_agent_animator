from manim import *

class AtomicElectrons(Scene):
    def construct(self):
        # Create a 3D scene
        scene = ThreeDScene()
        scene.set_camera_orientation(phi=75 * DEGREES, theta=30 * DEGREES)
        scene.set_background_color(BLACK)

        # Create the atomic nucleus
        nucleus = Sphere(radius=0.5, color=WHITE)
        self.add(nucleus)

        # Create the electrons
        electrons = []
        for i in range(10):
            electron = Sphere(radius=0.1, color=NEON_BLUE)
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
        self.play(scene.camera.animate.orbit(phi=360 * DEGREES, theta=360 * DEGREES, about_point=nucleus.get_center()))

        # Animate the electrons flowing and racing along the orbital pathways
        for electron in electrons:
            electron.animate.shift(RIGHT * 2)
            self.wait(0.1)

        # Add dynamic lighting and motion blur
        self.camera.set_lights(color=WHITE, intensity=2)
        self.camera.set_shutter_speed(0.001)
        self.camera.set_film_resolution(8192, 8192)
        self.camera.set_frame_rate(60)

        # Animate the scene
        self.wait(10)