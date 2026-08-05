"""WSGI entrypoint for production (gunicorn).

Run from the alpha-zero-engine directory:
    gunicorn --bind 0.0.0.0:8080 wsgi:app
"""

import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = ENGINE_DIR.parent

for path in (str(ENGINE_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.routes import create_app

app = create_app()
