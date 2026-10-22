import sys
from pathlib import Path

# Vercel ejecuta esta función desde la raíz; el código vive en backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402,F401
