from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Define the dimensions of the scene
        scene_width = 10
        scene_height = 10

        # Define the number of squares
        num_squares = 5

        # Define the size of each square
        square_size = 1

        # Define the duration of the animation
        duration = 2

        # Create a grid of squares
        grid = ArrayGrid(Square(square_size), num_squares, num_squares)

        # Set the color of each square's surface to a random RGB color
        for square in grid:
            square.set_fill(random_color(), opacity=0.5)

        # Create an animation that stacks the squares vertically
        stack_animation = grid.animate.shift(DOWN * scene_height / 2)

        # Create an animation that unstacks the squares vertically
        unstack_animation = stack_animation.animate.shift(UP * scene_height / 2)

        # Create a loop that repeats the stacking and unstacking animation
        loop_animation = AnimationGroup(
            stack_animation,
            unstack_animation,
            run_time=duration
        )

        # Create a loop that repeats the entire animation indefinitely
        self.add(grid)
        self.add(Loop(loop_animation))