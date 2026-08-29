"""Stress-test prompt registry for the finalized pipeline.

These are the user prompt variants used by the stress-test driver
(test_stress_run.py). They are kept separate from test_iteration_video.py's
PROMPTS so the presentation slugs/outputs are untouched.
"""

STRESS_PROMPTS = {
    "projectile_motion_3": """Make this look like something from a high-quality physics explainer. A projectile launches from the origin with initial velocity v₀ at angle θ. Show the launch vector breaking into horizontal and vertical components before the ball begins its flight. As the ball follows the parabola, continuously update the velocity vector so that its horizontal part remains unchanged while the vertical part decreases, becomes zero at the apex, and then points downward. Leave a faint trail behind the ball. Display the vertical motion equation without obscuring the graph. The axes should remain visible throughout. Use animation timing to make the sequence of launch → ascent → apex → descent obvious.""",
    "iron_atom_3": """I don't want the usual flat Bohr model. Make an abstract 3D Fe atom floating in darkness. The nucleus is a small glowing sphere-like cluster. Around it, three differently sized orbital structures are visible at different orientations rather than all appearing as one flat set of circles. Put 24 electron particles on them according to 2/8/14 shell occupancy and animate them around their paths. The paths should be subtle, almost like glowing traces in space. The nucleus should be warm and the electrons cool. The camera slowly changes perspective during the orbit sequence. No educational labels or text whatsoever. The result should look sophisticated and cinematic, but still clearly communicate that there are three shells and moving electrons.""",
    "kmeans_3": """There are points. Three centers. They should find their groups. Start messy, connect things to nearest center, move center to average, do it again. Black background, colorful groups. I want to be able to understand the algorithm just by watching it.""",
    "la_espada_3": """Produce a dark cinematic particle transformation. The phrase "la espada" is initially rendered in a saturated crimson-red against pure black. Reveal the phrase sequentially, one character at a time, with a slow luminous fade-in. Once the complete phrase has been established, convert the lettering into numerous small red particles and disperse them outward. After a short suspended interval, reverse the visual energy: particles accelerate toward a common diagonal structure and assemble into a single solid sword silhouette. The final sword must be contiguous and recognizable, including blade, guard, and hilt, with no visible holes or disconnected particle clusters. Hold the completed sword in silence for the final portion of the animation.""",
    "black_hole": """Show how a black hole bends spacetime and affects the path of nearby light.

I want a really visual 3D animation, not just text explaining it. Start with a dense grid representing spacetime, then have the center of the grid gradually curve downward into a deep gravitational well. Put a glowing black hole at the center and show several beams of light traveling past it.

The light should visibly bend as it passes near the black hole, with beams farther away bending less and beams closer to the center bending much more. Some light should curve around the black hole before escaping. Make the deformation of the grid respond spatially to the black hole so it feels like the space itself is being warped.

Use different colors to distinguish the spacetime grid, black hole, and light rays, but keep the overall look dark and cinematic. The camera should move slowly around the scene so the viewer can actually see the depth of the warped surface.

As the animation progresses, first show flat spacetime, then introduce the black hole and deformation, and finally animate multiple light rays through the curved spacetime. The final shot should clearly show the relationship between the depth of the gravitational well and the amount by which the light bends.

Avoid making it look like a simple textbook diagram. It should feel like a cinematic scientific visualization while still making the underlying physical concept understandable.""",
}
