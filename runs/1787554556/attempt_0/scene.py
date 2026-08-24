from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.title = Title("Stacked and Unstacked Square Slots", font_size=44)
        self.add(self.title)

        # Create a square slot
        square_slot = Square(side_length=2, fill_color=BLUE, fill_opacity=0.8)

        # Create a circle to represent the top of the stack
        circle = Circle(radius=1, color=RED)

        # Create a list to hold the slots
        slots = []
        for i in range(10):
            slots.append(square_slot.copy())

        # Create a list to hold the stacks
        stacks = []
        for i in range(5):
            stacks.append(circle.copy())

        # Function to create a stack
        def create_stack(slots, stacks):
            for i, slot in enumerate(slots):
                stacks[i].add(slot)
            stacks[i].move_to((i - 2) * 2, DOWN)

        # Function to remove a stack
        def remove_stack(stacks):
            for stack in stacks:
                stack.clear()
            stacks.clear()

        # Create stacks
        create_stack(slots, stacks)

        # Animate creating and removing stacks
        for _ in range(10):
            self.play(Create(slots[0]), run_time=1)
            create_stack(slots[1:], stacks)
            self.wait(1)
            self.play(FadeOut(slots[0]), run_time=1)
            remove_stack(stacks)

        # Animate removing all stacks
        self.play(FadeOut(slots), run_time=1)
        self.play(FadeOut(stacks), run_time=1)

        self.wait()