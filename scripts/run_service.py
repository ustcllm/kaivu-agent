from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service.main import create_app


if __name__ == "__main__":
    uvicorn.run(
        create_app(ROOT),
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )


