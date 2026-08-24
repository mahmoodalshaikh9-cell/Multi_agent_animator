from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Create a square slot
        square_slot = Square(side_length=2, color=WHITE, fill_color=BLUE, fill_opacity=0.5)
        square_slot.shift(LEFT * 3)

        # Create a circle that will be used to create the slots
        circle = Circle(radius=1, color=WHITE, fill_color=BLUE, fill_opacity=0.5)
        circle.shift(LEFT * 1)

        # Create a list to hold the slots
        slots = []

        # Create 5 slots
        for i in range(5):
            # Create a copy of the circle
            slot = circle.copy()
            # Rotate the slot
            slot.rotate(i * PI / 2)
            # Shift the slot to the right
            slot.shift(RIGHT * (i + 1))
            # Add the slot to the list
            slots.append(slot)

        # Create a list to hold the lights
        lights = []

        # Create 5 lights
        for i in range(5):
            # Create a circle that will be used to create the lights
            light = Circle(radius=0.1, color=RED, fill_color=RED, fill_opacity=1)
            # Rotate the light
            light.rotate(i * PI / 2)
            # Shift the light to the right
            light.shift(RIGHT * (i + 1))
            # Add the light to the list
            lights.append(light)

        # Create a list to hold the animations
        animations = []

        # Create the initial animation
        animations.append(Create(square_slot))
        animations.append(Create(slots[0]))
        animations.append(Create(lights[0]))

        # Create the animation to unstack the slots
        for i in range(1, 5):
            animations.append(Transform(slots[i - 1], slots[i]))
            animations.append(Transform(lights[i - 1], lights[i]))

        # Create the animation to stack the slots
        for i in range(4, 0, -1):
            animations.append(Transform(slots[i], slots[i - 1]))
            animations.append(Transform(lights[i], lights[i - 1]))

        # Play the animations
        self.play(*animations)
        self.wait()