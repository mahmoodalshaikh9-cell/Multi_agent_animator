import json
import requests
MODEL = "qwen2.5-coder:3b"
OLLAMA_URL = "http://localhost:11434/api/chat"

def clean_code(text: str) -> str:
    text = text.strip()

    if "```python" in text:
        text = text.split("```python", 1)[1]
        text = text.split("```", 1)[0]

    elif "```" in text:
        text = text.split("```", 1)[1]
        text = text.split("```", 1)[0]

    # Keep only the part beginning with the import.
    if "from manim import" in text:
        text = text[text.index("from manim import"):]

    return text.strip()

def ask_coder(prompt:str, temperature:float=0.2)->str:
    response = requests.post(OLLAMA_URL,json={
            "model": MODEL,
            "messages":[
                {
                    "role": "system",
                    "content": """
You are a Manim Community Edition coding agent.

Return ONLY Python code.

The code must:
- import from manim
- contain exactly one Scene subclass named GeneratedScene
- be directly runnable with:
  python -m manim scene.py GeneratedScene
- contain no markdown fences
- contain no explanations

Use only these well-known Manim APIs:
- Circle, Square, Rectangle, Dot, Line, Arrow, Text, NumberLine, Axes
- self.play(Create(...), Write(...), FadeIn(...), Transform(...))
- mobject.animate.shift / scale / move_to / set_color / rotate
- mobject.to_edge(UP), mobject.next_to(other, DOWN)
- self.wait()

Example of the exact style expected:

from manim import *

class GeneratedScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE)
        self.play(Create(circle))
        self.play(circle.animate.shift(RIGHT * 5))
        title = Text("Hello World", color=YELLOW).to_edge(UP)
        self.play(Write(title))
        self.wait()
""",
                },
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": temperature},
            "stream": False,
            
        }, timeout=300,)

    response.raise_for_status()
    return response.json()['message']["content"]

def extract_requirements(prompt: str) -> list[dict]:
    """Turn the user's request into a numbered checklist the vision model can verify item by item."""
    response = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": """
You convert an animation request into a short checklist of requirements.

Return ONLY valid JSON:

{
  "requirements": [
    {"id": "R1", "description": "...", "type": "visual or temporal", "required": true}
  ]
}

Rules:
- One requirement per distinct thing the user asked for.
- Each description must be checkable from still frames of the animation.
- Use 2 to 6 requirements. No explanations, no extra keys.
""",
            },
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0},
        "stream": False,
    }, timeout=300)

    response.raise_for_status()

    text = response.json()["message"]["content"].strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]

    fallback = [{"id": "R1", "description": prompt, "type": "visual", "required": True}]

    try:
        requirements = json.loads(text)["requirements"]
    except (json.JSONDecodeError, KeyError):
        # Fallback: evaluating against the whole prompt is weaker but never blocks the pipeline.
        return fallback

    return requirements if isinstance(requirements, list) and requirements else fallback

if __name__ == "__main__":
    code = ask_coder(
        "Create a simple animation that displays the text Hello World."
    )

    code = clean_code(code)

    print(code)

    with open("scene.py", "w", encoding="utf-8") as f:
        f.write(code)