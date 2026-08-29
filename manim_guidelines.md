````markdown
# Manim Community Edition — AI Coding Reference

You are writing executable Python code for Manim Community Edition (CE).

Official documentation:
https://docs.manim.community/en/stable/reference.html

Quickstart:
https://docs.manim.community/en/stable/tutorials/quickstart.html

## CRITICAL RULES

1. Only use real, documented Manim Community Edition APIs.
2. Never invent methods, properties, classes, or camera functions.
3. The first priority is successful rendering.
4. The second priority is satisfying the animation requirements.
5. Visual polish comes only after the scene is known to render.
6. Prefer simple, reliable Manim implementations over complicated effects.
7. Do not use Blender-specific APIs as if they were Manim APIs.
8. Do not claim Manim supports features that it does not actually provide.
9. If uncertain about an API, choose a simpler documented alternative.
10. When repairing code after a render error, actually remove or replace the code responsible for the error. Do not repeat the same broken code.

---

# 1. BASIC SCENE

Use `Scene` for ordinary 2D animation.

```python
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        circle = Circle()
        self.play(Create(circle))
        self.wait(1)
````

Documentation:
[https://docs.manim.community/en/stable/reference/manim.scene.scene.Scene.html](https://docs.manim.community/en/stable/reference/manim.scene.scene.Scene.html)

---

# 2. 3D SCENE

Use `ThreeDScene` for 3D objects and 3D camera movement.

```python
from manim import *

class GeneratedScene(ThreeDScene):
    def construct(self):
        sphere = Sphere(radius=1)
        self.add(sphere)

        self.set_camera_orientation(
            phi=65 * DEGREES,
            theta=-45 * DEGREES
        )

        self.begin_ambient_camera_rotation(
            rate=0.1,
            about="theta"
        )

        self.wait(5)

        self.stop_ambient_camera_rotation()
```

Documentation:
[https://docs.manim.community/en/stable/reference/manim.scene.three_d_scene.ThreeDScene.html](https://docs.manim.community/en/stable/reference/manim.scene.three_d_scene.ThreeDScene.html)

IMPORTANT:

Do NOT create a new camera and assign it to the scene:

```python
camera = ThreeDCamera()
self.camera = camera
```

This can cause:

```text
AttributeError: can't set attribute 'camera'
```

The scene already manages its camera.

Do NOT invent or use:

```python
self.set_camera(...)
self.camera.orbit(...)
self.camera.animate.orbit(...)
self.camera.set_perspective_camera(...)
self.camera.set_frame_shape(...)
```

Use documented `ThreeDScene` camera methods instead.

---

# 3. CAMERA MOVEMENT

For a cinematic camera orbit, prefer:

```python
self.set_camera_orientation(
    phi=65 * DEGREES,
    theta=-45 * DEGREES
)

self.begin_ambient_camera_rotation(
    rate=0.08,
    about="theta"
)

self.wait(10)

self.stop_ambient_camera_rotation()
```

Another option is:

```python
self.move_camera(
    phi=60 * DEGREES,
    theta=90 * DEGREES,
    run_time=5
)
```

Valid camera-related methods include:

```python
self.set_camera_orientation(...)
self.move_camera(...)
self.begin_ambient_camera_rotation(...)
self.stop_ambient_camera_rotation(...)
```

Documentation:
[https://docs.manim.community/en/stable/reference/manim.scene.three_d_scene.ThreeDScene.html](https://docs.manim.community/en/stable/reference/manim.scene.three_d_scene.ThreeDScene.html)

---

# 4. COMMON MOBJECTS

Useful objects include:

```python
Circle()
Square()
Dot()
Sphere()
Cube()
Line()
Arc()
ParametricFunction()
VGroup()
```

For a 3D electron:

```python
electron = Sphere(
    radius=0.12,
    color=BLUE
)
```

For a 2D electron:

```python
electron = Dot(
    radius=0.1,
    color=BLUE
)
```

---

# 5. PARAMETRIC PATHS

Use `ParametricFunction` to create smooth mathematical paths.

Example:

```python
path = ParametricFunction(
    lambda t: np.array([
        3 * np.cos(t),
        2 * np.sin(t),
        0
    ]),
    t_range=[0, TAU],
    color=BLUE
)
```

3D orbital:

```python
path = ParametricFunction(
    lambda t: np.array([
        3 * np.cos(t),
        2 * np.sin(t),
        0.5 * np.sin(2 * t)
    ]),
    t_range=[0, TAU],
    color=BLUE
)
```

IMPORTANT:

`ParametricFunction` uses the parameter `t` to construct the path.

Do NOT invent methods such as:

```python
path.get_point_at_time(...)
path.get_time(...)
```

Those are not valid ways to use `ParametricFunction`.

Documentation:
[https://docs.manim.community/en/stable/reference/manim.mobject.graphing.functions.ParametricFunction.html](https://docs.manim.community/en/stable/reference/manim.mobject.graphing.functions.ParametricFunction.html)

---

# 6. MOVING OBJECTS ALONG PATHS

The simplest reliable method is `MoveAlongPath`.

```python
electron = Sphere(
    radius=0.12,
    color=BLUE
)

self.add(electron)

self.play(
    MoveAlongPath(
        electron,
        path
    ),
    run_time=5,
    rate_func=linear
)
```

For continuous motion:

```python
self.play(
    MoveAlongPath(
        electron,
        path
    ),
    run_time=10,
    rate_func=linear
)
```

Documentation:
[https://docs.manim.community/en/stable/reference/manim.animation.movement.MoveAlongPath.html](https://docs.manim.community/en/stable/reference/manim.animation.movement.MoveAlongPath.html)

Do NOT invent path-time APIs.

---

# 7. MULTIPLE ELECTRONS

Create separate electrons for separate paths.

```python
paths = VGroup()

for i in range(4):
    path = ParametricFunction(
        lambda t, i=i: np.array([
            3 * np.cos(t + i * TAU / 4),
            2 * np.sin(t + i * TAU / 4),
            0.5 * np.sin(2 * t)
        ]),
        t_range=[0, TAU],
        color=BLUE
    )

    paths.add(path)

electrons = VGroup()

for path in paths:
    electron = Sphere(
        radius=0.12,
        color=BLUE
    )
    electrons.add(electron)

self.add(paths, electrons)

self.play(
    *[
        MoveAlongPath(
            electron,
            path,
            run_time=8,
            rate_func=linear
        )
        for electron, path in zip(electrons, paths)
    ]
)
```

Use `i=i` inside lambdas when generating paths in a loop so that each path retains the correct loop value.

---

# 8. UPDATERS

Mobjects can have functions that run every frame.

```python
dot.add_updater(
    lambda m, dt: m.shift(RIGHT * dt)
)
```

An updater commonly receives:

```python
m
dt
```

where `dt` is the time since the previous frame.

Documentation:
[https://docs.manim.community/en/stable/reference/manim.mobject.mobject.Mobject.html](https://docs.manim.community/en/stable/reference/manim.mobject.mobject.Mobject.html)

Prefer Mobject updaters over inventing custom frame/time APIs.

---

# 9. VALUETRACKER

Use `ValueTracker` when an object's position depends on an animated numerical value.

```python
tracker = ValueTracker(0)

dot = Dot()

dot.add_updater(
    lambda m: m.move_to(
        np.array([
            3 * np.cos(tracker.get_value()),
            2 * np.sin(tracker.get_value()),
            0
        ])
    )
)

self.add(dot)

self.play(
    tracker.animate.set_value(TAU),
    run_time=5,
    rate_func=linear
)
```

Documentation:
[https://docs.manim.community/en/stable/reference/manim.mobject.value_tracker.ValueTracker.html](https://docs.manim.community/en/stable/reference/manim.mobject.value_tracker.ValueTracker.html)

---

# 10. ANIMATION SYNTAX

Standard animation:

```python
self.play(Create(circle))
```

Animate a method:

```python
self.play(
    circle.animate.shift(RIGHT)
)
```

Multiple animations:

```python
self.play(
    circle.animate.shift(RIGHT),
    square.animate.shift(LEFT)
)
```

Set duration:

```python
self.play(
    circle.animate.shift(RIGHT),
    run_time=2
)
```

Use linear timing:

```python
self.play(
    circle.animate.shift(RIGHT),
    run_time=2,
    rate_func=linear
)
```

---

# 11. COMMON ANIMATIONS

```python
self.play(Create(circle))
self.play(FadeIn(circle))
self.play(FadeOut(circle))
self.play(Write(text))
```

---

# 12. GROUPS

Use `VGroup` for collections of Mobjects.

```python
objects = VGroup(
    circle,
    square,
    dot
)

self.add(objects)
```

Dynamic group:

```python
objects = VGroup()

for i in range(5):
    objects.add(
        Dot()
    )
```

---

# 13. COLORS

Common Manim colors:

```python
BLUE
GREEN
RED
YELLOW
WHITE
BLACK
PURPLE
ORANGE
PINK
```

For neon blue:

```python
NEON_BLUE = "#00FFFF"
```

Use:

```python
electron = Sphere(
    radius=0.12,
    color=NEON_BLUE
)
```

For unified orbital paths:

```python
PATH_COLOR = "#00FFFF"
```

Use exactly the same `PATH_COLOR` for every orbital pathway when the requirement says the pathways must have a unified color.

---

# 14. BLACK BACKGROUND

For a black background:

```python
self.camera.background_color = BLACK
```

Do this near the beginning of `construct()`.

Do NOT create a giant `NumberPlane` merely to make the background black.

---

# 15. GRADIENTS

Manim supports gradients on suitable Mobjects.

Example:

```python
circle.set_color_by_gradient(
    BLUE,
    PURPLE,
    PINK
)
```

However, this does NOT automatically create a fluid, animated liquid background.

If a prompt requests a liquid gradient, implement a simple reliable approximation using valid Manim objects and animations.

Do not invent a Manim "liquid gradient" API.

---

# 16. 3D OBJECTS AND LIGHTING

Use real 3D Mobjects such as:

```python
Sphere()
Cube()
```

Use `ThreeDScene` for 3D scenes.

Do not invent Blender-style lighting APIs.

Do not claim that Manim provides full photorealistic particle physics.

If the user asks for "photorealistic" or "8K", prioritize creating a valid Manim animation that approximates the visual appearance rather than inventing unsupported APIs.

---

# 17. MOTION BLUR

Do not invent a Manim API for motion blur.

If motion blur is requested, prioritize making motion visually obvious through:

* smooth animation
* appropriate run time
* multiple moving objects
* trails or fading effects if implemented using valid Manim objects

Do not write fictional APIs such as:

```python
object.enable_motion_blur()
self.camera.motion_blur = True
```

unless the installed Manim version explicitly documents them.

---

# 18. RENDERING CONFIGURATION

Do NOT configure resolution like this:

```python
self.camera.frame_shape = (1920, 1080)
```

Do NOT assume:

```python
self.camera.frame_rate = 60
```

is the correct way to configure output rendering.

Resolution and frame rate should be configured through Manim's rendering configuration or command-line options.

The scene code should focus on constructing the animation.

For example, the pipeline can control output settings separately from the generated scene code.

---

# 19. CAMERA AND SCENE API — IMPORTANT

The following approach is WRONG:

```python
camera = ThreeDCamera()
self.camera = camera
```

Do not replace the scene's camera.

Use:

```python
class GeneratedScene(ThreeDScene):
```

and then:

```python
self.set_camera_orientation(...)
```

or:

```python
self.begin_ambient_camera_rotation(...)
```

or:

```python
self.move_camera(...)
```

The scene owns and manages the camera.

---

# 20. NEVER USE THESE HALLUCINATED APIs

The following have caused real failures and must NEVER be generated:

```python
get_point_at_time()
get_time()
mobject_functions.get_time()
set_camera()
camera.orbit()
camera.animate.orbit()
self.camera.orbit()
set_frame_shape()
self.camera.set_frame_shape()
self.camera.set_perspective_camera()
self.camera = ThreeDCamera()
```

If a requested effect appears to require one of these, use a documented alternative.

---

# 21. COMMON REQUIREMENT → PREFERRED SOLUTION

"Move an object along a path."

Use:

```python
MoveAlongPath(object, path)
```

---

"Continuously change a numerical parameter."

Use:

```python
ValueTracker
```

---

"Move an object every frame."

Use:

```python
add_updater()
```

---

"Orbit a 3D camera."

Use:

```python
ThreeDScene
begin_ambient_camera_rotation()
```

or:

```python
ThreeDScene.move_camera()
```

---

"Create a smooth mathematical orbital path."

Use:

```python
ParametricFunction()
```

---

"Create a 3D electron."

Use:

```python
Sphere()
```

---

"Black background."

Use:

```python
self.camera.background_color = BLACK
```

---

"Multiple electrons moving simultaneously."

Use multiple `Sphere` objects and simultaneous `MoveAlongPath` animations:

```python
self.play(
    *[
        MoveAlongPath(
            electron,
            path,
            run_time=8,
            rate_func=linear
        )
        for electron, path in zip(electrons, paths)
    ]
)
```

---

# 22. RELIABILITY RULES

Before returning code:

1. Check every Manim method against known Manim CE APIs.
2. Do not invent methods.
3. Do not replace `self.camera`.
4. Use `ThreeDScene` for 3D camera work.
5. Use `MoveAlongPath` for straightforward path movement.
6. Use `ValueTracker` and `add_updater()` for continuous parameterized motion.
7. Keep the first implementation simple.
8. Make sure the code can render before adding visual effects.
9. Never implement Blender-specific features as if they were Manim features.
10. If uncertain about an API, choose a simpler documented solution.
11. If a previous attempt produced a runtime error, do not repeat the code responsible for that error.
12. When repairing code, change the actual cause of the error.
13. Do not waste attempts on unsupported visual effects.
14. Prefer deterministic animation mechanisms.
15. The final output must be executable Python code, not pseudocode.

---

# 23. REPAIR RULES

When the renderer returns an error, carefully inspect the traceback.

Example:

```text
AttributeError: can't set attribute 'camera'
```

The incorrect code is:

```python
self.camera = camera
```

The repair must REMOVE or replace that line.

Do not simply rewrite the surrounding code while keeping:

```python
self.camera = camera
```

If an API is reported as nonexistent:

```text
AttributeError: ... get_point_at_time
```

Do not continue using:

```python
path.get_point_at_time(...)
```

Replace it with a documented mechanism such as:

```python
MoveAlongPath()
```

or a valid updater/ValueTracker implementation.

---

# 24. PRIORITY ORDER FOR GENERATED SCENES

Always prioritize requirements in this order:

1. Valid Python.
2. Valid Manim CE APIs.
3. Successful Manim rendering.
4. Required objects exist.
5. Required animation actually happens.
6. Temporal requirements are satisfied.
7. Visual requirements are satisfied.
8. Camera movement works.
9. Visual polish.
10. Advanced effects.

A simple scene that renders correctly is better than a sophisticated scene that crashes.

---

# 25. EXAMPLE: RELIABLE ELECTRON ORBIT SCENE

This is a good baseline pattern for an atomic animation:

```python
from manim import *
import numpy as np

class GeneratedScene(ThreeDScene):
    def construct(self):

        self.camera.background_color = BLACK

        nucleus = Sphere(
            radius=0.5,
            color=RED
        )

        self.add(nucleus)

        PATH_COLOR = "#00FFFF"
        ELECTRON_COLOR = "#00FFFF"

        paths = VGroup()
        electrons = VGroup()

        for i in range(4):

            phase = i * TAU / 4

            path = ParametricFunction(
                lambda t, phase=phase: np.array([
                    3 * np.cos(t + phase),
                    1.8 * np.sin(t + phase),
                    0.5 * np.sin(2 * t + phase)
                ]),
                t_range=[0, TAU],
                color=PATH_COLOR
            )

            paths.add(path)

            electron = Sphere(
                radius=0.12,
                color=ELECTRON_COLOR
            )

            electrons.add(electron)

        self.add(paths)

        self.set_camera_orientation(
            phi=65 * DEGREES,
            theta=-45 * DEGREES
        )

        self.add(electrons)

        self.play(
            *[
                MoveAlongPath(
                    electron,
                    path,
                    run_time=8,
                    rate_func=linear
                )
                for electron, path in zip(electrons, paths)
            ]
        )

        self.wait(1)
```

Use this type of implementation as a starting point rather than inventing new APIs.

---

# OFFICIAL DOCUMENTATION

Main reference:
[https://docs.manim.community/en/stable/reference.html](https://docs.manim.community/en/stable/reference.html)

Quickstart:
[https://docs.manim.community/en/stable/tutorials/quickstart.html](https://docs.manim.community/en/stable/tutorials/quickstart.html)

Scenes:
[https://docs.manim.community/en/stable/reference_index/scenes.html](https://docs.manim.community/en/stable/reference_index/scenes.html)

Animations:
[https://docs.manim.community/en/stable/reference_index/animations.html](https://docs.manim.community/en/stable/reference_index/animations.html)

ThreeDScene:
[https://docs.manim.community/en/stable/reference/manim.scene.three_d_scene.ThreeDScene.html](https://docs.manim.community/en/stable/reference/manim.scene.three_d_scene.ThreeDScene.html)

ThreeDCamera:
[https://docs.manim.community/en/stable/reference/manim.camera.three_d_camera.ThreeDCamera.html](https://docs.manim.community/en/stable/reference/manim.camera.three_d_camera.ThreeDCamera.html)

Mobject:
[https://docs.manim.community/en/stable/reference/manim.mobject.mobject.Mobject.html](https://docs.manim.community/en/stable/reference/manim.mobject.mobject.Mobject.html)

ValueTracker:
[https://docs.manim.community/en/stable/reference/manim.mobject.value_tracker.ValueTracker.html](https://docs.manim.community/en/stable/reference/manim.mobject.value_tracker.ValueTracker.html)

MoveAlongPath:
[https://docs.manim.community/en/stable/reference/manim.animation.movement.MoveAlongPath.html](https://docs.manim.community/en/stable/reference/manim.animation.movement.MoveAlongPath.html)

ParametricFunction:
[https://docs.manim.community/en/stable/reference/manim.mobject.graphing.functions.ParametricFunction.html](https://docs.manim.community/en/stable/reference/manim.mobject.graphing.functions.ParametricFunction.html)

```
```
