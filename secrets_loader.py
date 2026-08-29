"""Resolve API keys/secrets from Streamlit secrets, env vars, or the local
secrets.toml file.

Priority order (first non-empty wins):
  1. environment variables
  2. Streamlit's secrets store (st.secrets, backed by .streamlit/secrets.toml
     locally and the dashboard secrets on Streamlit Community Cloud)
  3. the repo-root secrets.toml file (local script runs)

Each caller passes its key plus optional aliases (e.g. "deepseek" and
"DEEPSEEK_API_KEY") so the same code works across deployment targets.
"""
import os
from pathlib import Path

try:
    import streamlit as st
except Exception:  # pragma: no cover - streamlit not installed/importable
    st = None

_REPO_ROOT = Path(__file__).parent


def _toml_fallback() -> dict:
    path = _REPO_ROOT / "secrets.toml"
    try:
        if path.exists():
            import toml
            return toml.load(path)
    except Exception:
        pass
    return {}


def get(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value

    if st is not None:
        try:
            for name in names:
                value = str(st.secrets.get(name) or "").strip()
                if value:
                    return value
        except Exception:
            pass

    data = _toml_fallback()
    for name in names:
        value = str(data.get(name) or "").strip()
        if value:
            return value

    return default
