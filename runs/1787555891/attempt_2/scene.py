from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Create a square slot
        square = Square(side_length=2, color=BLUE)
        square.set_fill(color=WHITE, opacity=0.5)
        square.set_stroke(color=BLACK, width=2)
        
        # Create a number line for the slots
        number_line = NumberLine(x_range=[-5, 5, 1], numbers_with_arrows=True)
        number_line.add_numbers([-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5])
        number_line.set_color(BLUE)
        
        # Create a list of slots
        slots = [square.copy() for _ in range(10)]
        
        # Arrange the slots on the number line
        for i, slot in enumerate(slots):
            slot.move_to(number_line.number_to_point(i))
        
        # Create a list to hold the animations
        animations = []
        
        # Animate stacking the slots
        for i in range(5):
            for j in range(i + 1, 10):
                animations.append(Transform(slots[i], slots[j]))
            self.play(*animations)
            animations = []
        
        # Animate unstacking the slots
        for i in range(4, -1, -1):
            for j in range(i + 1, 10):
                animations.append(Transform(slots[i], slots[j]))
            self.play(*animations)
            animations = []
        
        # Add the number line to the scene
        self.add(number_line)
        
        # Add the slots to the scene
        self.add(*slots)
        
        # Wait for the animation to finish
        self.wait()