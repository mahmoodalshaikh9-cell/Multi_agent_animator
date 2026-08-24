from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Create the initial stacked squares
        squares = VGroup(*[Square(color=hue_to_rgb(i/6), fill_opacity=1, stroke_width=0) for i in range(6)])

        # Define a function to rotate the squares
        def rotate_squares(squares, angle):
            squares.rotate(angle, about_point=squares.get_center())

        # Create a toggle for the animation
        toggle = Toggle("Stack", "Unstack", color=WHITE)

        # Define the animation function
        def animate_toggle(toggle):
            self.wait(1)
            if toggle.is_on():
                rotate_squares(squares, PI)
            else:
                rotate_squares(squares, 0)
            self.wait(1)

        # Add the toggle to the scene
        self.add(toggle)
        self.wait(1)

        # Start the animation
        self.play(ApplyMethod(animate_toggle, toggle))