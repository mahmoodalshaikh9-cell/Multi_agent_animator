import json
import os
from pathlib import Path

from flask import Flask, Response, send_from_directory

ROOT = Path(__file__).resolve().parent

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.route("/demo/<path:name>")
def demo(name: str):
    return send_from_directory(ROOT / "demo", name)


@app.route("/demo/run.json")
def run_json():
    path = ROOT / "demo" / "run.json"
    if path.is_file():
        return send_from_directory(ROOT / "demo", "run.json")
    default = {
        "prompt": "Explain how streamlit compiles python into UI",
        "first_attempt": "attempt_1",
        "last_attempt": "attempt_4",
        "generated_at": "n/a",
    }
    return Response(
        json.dumps(default),
        mimetype="application/json",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
