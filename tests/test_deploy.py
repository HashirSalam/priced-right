"""The deployment files stay in step with the lock file, so the server runs the versions the model was saved with."""
from pathlib import Path

from priced_right.final_model import load

ROOT = Path(__file__).resolve().parents[1]


def pins(name: str) -> dict[str, str]:
    lines = (ROOT / name).read_text().splitlines()
    return {line.split("==")[0].lower(): line.split("==")[1] for line in lines if "==" in line and not line.startswith("#")}


def test_app_requirements_match_the_lock_file():
    app, lock = pins("requirements-app.txt"), pins("requirements-lock.txt")
    shared = set(app) & set(lock)
    assert {"flask", "numpy", "pandas", "scikit-learn"} <= shared
    assert {name: app[name] for name in shared} == {name: lock[name] for name in shared}


def test_server_scikit_learn_is_the_version_that_saved_the_model():
    assert pins("requirements-app.txt")["scikit-learn"] == load()["sklearn_version"]


def test_render_runs_the_flask_app_with_gunicorn():
    blueprint = (ROOT / "render.yaml").read_text()
    assert "gunicorn" in pins("requirements-app.txt")
    assert "startCommand: gunicorn priced_right.app:app " in blueprint
    assert "buildCommand: pip install -r requirements-app.txt -c requirements-lock.txt" in blueprint   # lock as constraint
