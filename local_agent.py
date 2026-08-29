import ast
import builtins
import importlib
import inspect
import json
import re
import requests
import manim
import toml
from pathlib import Path
with open("manim_guidelines.md", "r", encoding="utf-8") as file:
    manim_guidelines = file.read()

secrets_data = toml.load(Path(__file__).parent / "secrets.toml")
key = secrets_data.get("openrouter_cohere_key", "")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_API_KEY = secrets_data.get("deepseek", "")

MODEL = "google/gemini-2.5-flash"
OLLAMA_URL = "https://openrouter.ai/api/v1/chat/completions"
URL = "https://openrouter.ai/api/v1/chat/completions"
Qwen = 'qwen/qwen3.8-flash'
gemni_vision ='google/gemini-2.5-flash'

def clean_code(text: str) -> str:
    if not text:
        return ""
    text = text.strip()

    if "```python" in text:
        text = text.split("```python", 1)[1]
        text = text.split("```", 1)[0]

    elif "```" in text:
        text = text.split("```", 1)[1]
        text = text.split("```", 1)[0]

    
    if "from manim import" in text:
        text = text[text.index("from manim import"):]

    text = re.sub(
        r'^\s*config\.(pixel_width|pixel_height|frame_rate|pixel_density)\s*=.*$',
        '',
        text,
        flags=re.MULTILINE,
    )

    return text.strip()

def ask_coder(prompt:str, temperature:float=0.2)->str:
    response = requests.post(OLLAMA_URL,headers=headers,json={
            "model": MODEL,
            "messages":[
                {
                    "role": "system",
                    "content": manim_guidelines
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "stream": False,
        }, timeout=300)

    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
headers = {
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
}

def extract_requirements(prompt: str) -> list[dict]:
    """Turn the user's request into a numbered checklist the vision model can verify item by item."""
    response = requests.post(OLLAMA_URL,headers=headers ,json={
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
        "temperature": 0.2,
        "stream": False,
    }, timeout=300)

    response.raise_for_status()

    text = response.json()["choices"][0]["message"]["content"].strip()

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


def _collect_target(target: ast.expr, defined: set) -> None:
    if isinstance(target, ast.Name):
        defined.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            _collect_target(element, defined)
    elif isinstance(target, ast.Starred):
        _collect_target(target.value, defined)
    elif isinstance(target, ast.Attribute):
        defined.add(target.attr)


def find_unknown_symbols(code: str) -> list[str]:
    """Return names/attributes in the code that do not exist in Manim CE, builtins, or the code itself.

    Catches hallucinated APIs (e.g. set_camera, repeat_forever) before wasting a render.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    allowed = set(dir(builtins)) | {""}

    def add_namespace(obj) -> None:
        allowed.update(dir(obj))

    add_namespace(object)
    add_namespace([])
    add_namespace({})
    add_namespace("")
    add_namespace(manim)

    for name in dir(manim):
        obj = getattr(manim, name, None)
        if inspect.isclass(obj) or name == "config":
            add_namespace(obj)

    numpy_module = getattr(manim, "np", None)

    if numpy_module is not None:
        add_namespace(numpy_module)

        random_module = getattr(numpy_module, "random", None)

        if random_module is not None:
            add_namespace(random_module)

    def add_module(module_name: str) -> None:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            return
        add_namespace(module)

    defined = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                _collect_target(target, defined)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            _collect_target(node.target, defined)
        elif isinstance(node, ast.For):
            _collect_target(node.target, defined)
        elif isinstance(node, ast.comprehension):
            _collect_target(node.target, defined)
        elif isinstance(node, ast.Global):
            defined.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.asname or alias.name.split(".")[0]
                defined.add(root)
                add_module(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if any(alias.name == "*" for alias in node.names):
                add_module(node.module)
            else:
                for alias in node.names:
                    if alias.name != "*":
                        defined.add(alias.asname or alias.name)

    unknown = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in allowed and node.id not in defined:
                unknown.add(node.id)

    return sorted(unknown)


# if __name__ == "__main__":
#     code = ask_coder(
#         "Create a simple animation that displays the text Hello World."
#     )

#     code = clean_code(code)

#     print(code)

#     with open("scene.py", "w", encoding="utf-8") as f:
#         f.write(code)



PLANNER_SYSTEM_PROMPT = """
You are an animation scene planning agent.

Your job is to translate a user's animation request into a
clear implementation plan for a separate Manim coding agent.

The user may describe their desired animation poorly or vaguely.
Infer the likely visual intent conservatively.

Preserve the user's explicit requirements.
Do not invent major objects, actions, or narrative elements
that are not supported by the request.

The plan should describe:

- What objects should appear
- Their spatial relationships
- What happens at the beginning
- What happens during the main animation
- What happens at the end
- How objects move
- Camera movement
- Timing and sequencing
- Visual style
- Important constraints

Do NOT write Python.
Do NOT write Manim code.
Do NOT explain your reasoning.

Return ONLY valid JSON in this format:

{
  "scene_plan": {
    "composition": "...",
    "objects": ["..."],
    "sequence": [
      "...",
      "...",
      "..."
    ],
    "motion": ["..."],
    "camera": "...",
    "style": "...",
    "constraints": ["..."],
    "three_d": true or false
  }
}

Set "three_d" to true ONLY when the request genuinely needs three-dimensional
rendering: volumetric or shaded shapes (spheres, atoms, molecular models),
orbital planes at different spatial depths, an atom with shells/rings, or an
orbiting / depth-revealing camera movement. Keep it false for flat 2D
educational scenes (labeled plots, vector diagrams, projected motion graphs).
"""


def planning(prompt: str, requirements: list[dict]) -> dict:

    response = requests.post(
        URL,
        headers=headers,
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": PLANNER_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": f"""
Original user request:

{prompt}

Extracted requirements:

{requirements}

Create the scene plan.
""",
                },
            ],
            "temperature": 0.2,
            "stream": False,
        },
        timeout=300,
    )

    response.raise_for_status()

    text = response.json()["choices"][0]["message"]["content"].strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]

    return json.loads(text)

reconstructing_SYSTEM_PROMPT = 'you are a creative client assistant. your job is to help translate the users intent to a well refiend coding ' \
'agent prompt to produce sensible manim animations. on each iteration, add some conceptual improvment to the animation for clarity and better idea communication. do not make huge changes, imporve the animation little by little ineach animation'
def prompt_reconstruct(prompt: str, requirements: list[dict], failures: str = "") -> str:
    response = requests.post(
            URL,
            headers=headers,
            json={
                "model": gemni_vision,
                "messages": [
                    {
                        "role": "system",
                        "content": reconstructing_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": f"""
Original user request:

{prompt}

Extracted requirements:

{requirements}

Evaluation feedback:

{failures}

Refine the user request a little so the animation communicates the idea
more clearly. Do NOT write Python or Manim code.

Return ONLY the refined prompt, no explanations.
""",
                    },
                ],
                "temperature": 0.2,
                "stream": False,
            },
            timeout=300,
        )

    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"].strip()
    