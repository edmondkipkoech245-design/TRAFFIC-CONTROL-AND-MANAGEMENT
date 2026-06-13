import os
import sys

# ensure project root is on path so we can import backend
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.main import app  # expose FastAPI app as `app` for Vercel ASGI runtime
