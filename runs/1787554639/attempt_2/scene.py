from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Define the size of the square slots
        slot_size = 2

        # Create a square slot
        slot = Square(side_length=slot_size, color=WHITE)

        # Define the color for the lights
        light_color = RED

        # Create a function to fill the surface of the slot with lights
        def fill_with_lights(slot):
            light = Circle(radius=slot_size / 4, color=light_color, fill_opacity=0.5)
            light.move_to(slot.get_center())
            return light

        # Create a list to store the slots
        slots = [slot.copy() for _ in range(5)]

        # Function to animate the slots
        def animate_slots():
            self.play(FadeIn(slots), run_time=1)
            self.play(FadeOut(slots), run_time=1)
            self.play(FadeIn(slots), run_time=1)
            self.play(FadeOut(slots), run_time=1)

        # Animate the slots
        animate_slots()